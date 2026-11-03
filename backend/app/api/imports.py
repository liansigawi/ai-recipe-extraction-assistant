"""Importing a recipe: a model reads the text, the backend checks the answer, a draft is saved.

    GET  /api/extraction          can imports use the model right now, and which one?
    POST /api/imports/text        pasted text -> a saved draft (status "draft") with review issues
    POST /api/imports/instagram   a post's address -> its caption, read from Instagram -> a saved draft
    POST /api/imports/link        any recipe link: Instagram's importer for a post, the website importer
                                  for any other page (the host name decides)

The model is Claude or a local model through Ollama (RECIPES_EXTRACTOR, app/extraction/choose.py).
The draft is saved at once, together with the original text, so nothing is lost; the person
then reviews it in the editor and saves it explicitly. If anything fails before that,
nothing is saved and the page keeps the pasted text.
"""

import functools
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import httpx2

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud, media
from app.api.shared_runs import SharedRuns
from app.config import load_settings
from app.db import get_session
from app.errors import ERROR_RESPONSES, ApiError, ErrorResponse
from app.extraction.choose import extraction_info as current_extraction_info
from app.extraction.choose import make_extractor
from app.extraction.claude import Extractor
from app.extraction.review import is_recipe, make_draft, manual_draft
from app.extraction.structured import structured_draft
from app.importers import website
from app.importers.website import StructuredRecipe, WebReader, WebsiteError
from app.importers.instagram import (
    CaptionRetrieval,
    FetchOutcome,
    InstagramRef,
    InvalidInstagramUrl,
    parse_instagram_url,
    retrieve_caption_blocking,
)
from app.schemas import (
    Creator,
    ExtractionInfo,
    InstagramImport,
    Issue,
    LinkedRecipe,
    LinkImport,
    Recipe,
    RecipeInput,
    Source,
    TextImport,
)

IMPORT_ERRORS = {
    **ERROR_RESPONSES,
    502: {"model": ErrorResponse, "description": "The model failed or gave an unusable answer"},
    503: {"model": ErrorResponse, "description": "No API key, Ollama not running, or the model is busy"},
    504: {"model": ErrorResponse, "description": "The model did not answer in time"},
}

INSTAGRAM_ERRORS = {
    **IMPORT_ERRORS,
    409: {
        "model": ErrorResponse,
        "description": "The post is already in the notebook (duplicate_link), or only a preview of its caption was read",
    },
    429: {"model": ErrorResponse, "description": "Instagram asks to wait before reading more posts"},
}

LINK_ERRORS = {
    **INSTAGRAM_ERRORS,
    422: {"model": ErrorResponse, "description": "Not a readable address, a private address, no recipe, or several recipes"},
}

router = APIRouter(prefix="/api", tags=["imports"])
log = logging.getLogger("uvicorn.error")

SessionDep = Annotated[Session, Depends(get_session)]
ExtractorFactory = Callable[[], Extractor]


IMPORTS_UNDER_WAY = SharedRuns()


def shared_when_repeated(endpoint: Callable[..., Recipe]) -> Callable[..., Recipe]:
    """The same import sent again while it is still running shares that run: one generation on the
    model, one draft, the same answer for both (app/api/shared_runs.py)."""

    @functools.wraps(endpoint)
    def run(data: TextImport | InstagramImport | LinkImport, *args: Any, **kwargs: Any) -> Recipe:
        key = f"{endpoint.__name__} {data.model_dump_json()}"
        return IMPORTS_UNDER_WAY.run(key, lambda: endpoint(data, *args, **kwargs))

    return run


def get_extractor_factory() -> ExtractorFactory:
    """FastAPI dependency: how to get an extractor. Tests replace it with a stand-in.

    Settings are read when an import starts, so a key or a model choice added to .env works
    without restarting the backend.
    """
    return lambda: make_extractor(load_settings())


CaptionRetriever = Callable[[InstagramRef], CaptionRetrieval]


def get_caption_retriever() -> CaptionRetriever:
    """FastAPI dependency: how to read a post. Tests replace it, so no test ever reaches Instagram."""
    return retrieve_caption_blocking


def get_web_reader() -> WebReader:
    """FastAPI dependency: how to read web pages and pictures. Tests replace it, so no test reaches a website."""
    return WebReader()


@router.get("/extraction")
def extraction_info() -> ExtractionInfo:
    """Whether imports can use the model now, which one, and whether the text stays on this computer.

    Never returns the API key itself.
    """
    return current_extraction_info(load_settings())


@router.post("/imports/text", status_code=status.HTTP_201_CREATED, responses=IMPORT_ERRORS)
@shared_when_repeated
def import_text(
    data: TextImport,
    session: SessionDep,
    new_extractor: Annotated[ExtractorFactory, Depends(get_extractor_factory)],
) -> Recipe:
    """Pasted text -> a saved draft for review, with the original text kept beside it.

    With use_model = false, the text is saved as a draft without a model, to fill in by hand.
    With a url (the Instagram post or the recipe page the text was copied from, after reading it
    failed), the address is kept with the original and becomes the recipe's source.
    """
    url = _link_url(data.url) if data.url is not None and data.url.strip() else None
    if url is not None and not data.allow_duplicate:
        _refuse_duplicate(session, url)
    draft, model = _draft(data.text, data.use_model, session, new_extractor)
    if url is not None:
        kind = "instagram" if website.is_instagram(url) else "website"
        draft = draft.model_copy(update={"sources": [Source(kind=kind, url=url)]})
    if data.possibly_incomplete:
        draft = draft.model_copy(update={"issues": [CAPTION_INCOMPLETE, *draft.issues]})
    return crud.create_import(session, draft, original_text=data.text, model=model, url=url)


# The page's message comes from the code (instagram_<outcome>); these are for the API's own users.
_READ_FAILURES: dict[FetchOutcome, tuple[int, str]] = {
    FetchOutcome.LOGIN_REQUIRED: (502, "Instagram asks to log in to see this post."),
    FetchOutcome.UNAVAILABLE: (502, "Instagram says this post isn't available (deleted, private, or temporarily)."),
    FetchOutcome.RATE_LIMITED: (429, "Instagram asks to wait before reading more posts."),
    FetchOutcome.NO_CAPTION: (422, "The post has no caption."),
    FetchOutcome.CAPTION_NOT_FOUND: (502, "The post's page loaded, but no caption was recognized on it."),
    FetchOutcome.TIMEOUT: (504, "Instagram did not answer in time."),
    FetchOutcome.ERROR: (502, "The post could not be read."),
}

CAPTION_INCOMPLETE = Issue(
    kind="caption_incomplete",
    message="הכיתוב נלקח מתצוגה מקדימה של הפוסט, וייתכן שהוא קטוע. השוו לפוסט באינסטגרם והשלימו את החסר.",
)


@router.post("/imports/instagram", status_code=status.HTTP_201_CREATED, responses=INSTAGRAM_ERRORS)
@shared_when_repeated
def import_instagram(
    data: InstagramImport,
    session: SessionDep,
    new_extractor: Annotated[ExtractorFactory, Depends(get_extractor_factory)],
    retrieve: Annotated[CaptionRetriever, Depends(get_caption_retriever)],
    media_folder: Annotated[Path, Depends(media.get_media_root)],
    transport: Annotated[httpx2.BaseTransport | None, Depends(media.get_media_transport)],
) -> Recipe:
    """A public post's address -> its caption, read from Instagram -> a saved draft, as for pasted text.

    The full caption and the post's address are kept with the original; the address is also the
    recipe's (editable) source, with the post's author and co-authors. Nothing is saved when the post
    cannot be read or only a preview of its caption was found: the error says why, and its details
    carry the address and any caption read, so the page can offer pasting the caption instead.
    """
    url = _canonical_url(data.url)
    if not data.allow_duplicate:
        _refuse_duplicate(session, url)  # before anything is fetched
    session.commit()  # nothing is read from the database during the page loads
    retrieval = retrieve(parse_instagram_url(url))
    log.info(
        "Instagram %s: %s (%s)", url, retrieval.outcome,
        ", ".join(f"{a.page} {a.outcome} {a.elapsed_ms} ms" for a in retrieval.attempts),
    )
    details = {"url": url, "caption": retrieval.caption, "attempts": [a.model_dump(mode="json") for a in retrieval.attempts]}
    if retrieval.outcome is FetchOutcome.CAPTION_INCOMPLETE:
        raise ApiError(409, "instagram_caption_incomplete", "Only a preview of the caption was read; it may be cut off.", details)
    if retrieval.outcome is not FetchOutcome.CAPTION_FOUND or not retrieval.caption:
        status_code, message = _READ_FAILURES.get(retrieval.outcome, _READ_FAILURES[FetchOutcome.ERROR])
        raise ApiError(status_code, f"instagram_{retrieval.outcome}", message, details)

    try:
        draft, model = _draft(retrieval.caption, data.use_model, session, new_extractor)
    except ApiError as error:
        # The caption was read: hand it back, so the page can keep it for another try or for saving by hand.
        raise ApiError(error.status_code, error.code, error.message, _merged(error.details, details)) from None
    # The credit comes from the post's data (the account and its display name), never from the model.
    people = [person for person in (retrieval.author, *retrieval.coauthors) if person is not None]
    creators = [Creator(name=person.full_name, username=person.username) for person in people]
    draft = draft.model_copy(update={"sources": [Source(kind="instagram", url=url, creators=creators)]})
    details = {
        "author": creators[0].model_dump() if retrieval.author is not None else None,
        "coauthors": [creator.model_dump() for creator in creators[1 if retrieval.author is not None else 0 :]],
    }
    created = crud.create_import(
        session, draft, original_text=retrieval.caption, model=model, kind="instagram", url=url,
        retrieved_from=retrieval.retrieved_from, source_details=details,
    )
    _attach_media(session, created.id, parse_instagram_url(url), retrieval, media_folder, transport)
    return crud.get_recipe(session, created.id)


@router.post("/imports/link", status_code=status.HTTP_201_CREATED, responses=LINK_ERRORS)
@shared_when_repeated
def import_link(
    data: LinkImport,
    session: SessionDep,
    new_extractor: Annotated[ExtractorFactory, Depends(get_extractor_factory)],
    retrieve: Annotated[CaptionRetriever, Depends(get_caption_retriever)],
    reader: Annotated[WebReader, Depends(get_web_reader)],
    media_folder: Annotated[Path, Depends(media.get_media_root)],
    transport: Annotated[httpx2.BaseTransport | None, Depends(media.get_media_transport)],
) -> Recipe:
    """Any recipe link -> a saved draft. The host name decides, not a model: an Instagram link goes to
    the Instagram importer (caption, credit, media and the duplicate check as before), any other page
    to the website importer."""
    if website.is_instagram(data.url):
        request = InstagramImport(url=data.url, use_model=data.use_model, allow_duplicate=data.allow_duplicate)
        return import_instagram(request, session, new_extractor, retrieve, media_folder, transport)
    return _import_website(data, session, new_extractor, reader, media_folder)


def _merged(details: Any, more: dict[str, Any]) -> dict[str, Any]:
    """An error's own details (say, the model's time limit) with the import's (the address, the caption)."""
    return {**details, **more} if isinstance(details, dict) else more


def _website_error(error: WebsiteError, url: str) -> ApiError:
    return ApiError(error.status, f"website_{error.code}", error.message, {"url": url})


def _import_website(data: LinkImport, session: Session, new_extractor: ExtractorFactory, reader: WebReader, folder: Path) -> Recipe:
    """A recipe page -> a saved draft. Its Schema.org recipe data, when it has it, in its own words (a
    model only chooses the category); otherwise its main text, read by the model as pasted text is.
    Nothing is saved when the page cannot be read, is not a recipe, or has several recipes and none
    is clearly its own: the error says why, with the address, so the page can offer pasting the text."""
    try:
        url = website.check_url(data.url)
    except WebsiteError as error:
        raise _website_error(error, data.url.strip()) from None
    if not data.allow_duplicate:
        _refuse_duplicate(session, url)  # before anything is fetched
    session.commit()  # nothing is read from the database while the page loads
    try:
        page = reader.page(url)
    except WebsiteError as error:
        log.info("Website %s: %s (%s)", url, error.code, error.message)
        raise _website_error(error, url) from None
    analysis = website.analyze(page)
    log.info(
        "Website %s: %s", url,
        f"recipe data ({analysis.recipe.found_in}{', ' + ' and '.join(analysis.recipe.from_page) + ' as the page shows them' if analysis.recipe.from_page else ''})" if analysis.recipe else f"{len(analysis.ambiguous)} recipes" if analysis.ambiguous else f"main text, {len(analysis.text)} characters",
    )
    details = {"url": url}
    if analysis.blocked:
        raise ApiError(502, "website_blocked", "The site showed a bot check instead of the page.", details)
    if analysis.ambiguous:
        raise ApiError(
            422, "website_ambiguous", "The page has several recipes, and none is clearly its own.",
            {"url": url, "recipes": analysis.ambiguous[:10]},
        )
    if analysis.url != url and not data.allow_duplicate:
        _refuse_duplicate(session, analysis.url)  # the same page under its own address
    recipe = analysis.recipe
    if recipe is not None:
        original = website.render(recipe)
        draft, model = _structured_draft(recipe, original, data.use_model, session, new_extractor)
        retrieved_from = recipe.found_in
        image = recipe.image or analysis.image
    else:
        if len(analysis.text) < website.MIN_TEXT_CHARACTERS:
            raise ApiError(422, "website_no_recipe", "No recipe was found on the page.", details)
        original = analysis.text
        try:
            draft, model = _draft(original, data.use_model, session, new_extractor)
        except ApiError as error:
            if error.code == "not_a_recipe":
                raise ApiError(422, "website_no_recipe", "The page's text was read, but the model found no recipe in it.", details) from None
            raise ApiError(error.status_code, error.code, error.message, _merged(error.details, details)) from None
        if data.use_model and (not any(group.ingredients for group in draft.ingredient_groups) or not any(group.steps for group in draft.step_groups)):
            # A recipe page whose text has no ingredient lines, or no steps: the page shows them some
            # other way (seen live: lists drawn by the page's scripts, absent from the page it sends).
            # Nothing half-filled is saved; the person can paste the recipe from the page.
            raise ApiError(422, "website_incomplete", "Only part of the recipe is in the page's text (no ingredients, or no steps).", details)
        if analysis.truncated:
            draft = draft.model_copy(update={"issues": [*draft.issues, WEBSITE_TEXT_CUT]})
        retrieved_from = "page_text"
        image = analysis.image
    # The credit comes from the page (its recipe data, else its metadata, else the site's name), never from the model.
    names = (recipe.authors if recipe is not None else []) or ([analysis.author] if analysis.author else [])
    creators = [Creator(name=name[:200]) for name in names[:3]] or ([Creator(name=analysis.site_name[:200])] if analysis.site_name else [])
    draft = draft.model_copy(update={"sources": [Source(kind="website", url=analysis.url, creators=creators)]})
    source_details = {
        "author": creators[0].model_dump() if creators else None,
        "coauthors": [creator.model_dump() for creator in creators[1:]],
        "site_name": analysis.site_name,
        "image": image,
        "structured_data": website.trimmed(recipe.raw) if recipe is not None else None,
    }
    created = crud.create_import(
        session, draft, original_text=original, model=model, kind="website", url=analysis.url,
        retrieved_from=retrieved_from, source_details=source_details,
    )
    if image is not None:
        _attach_website_image(session, created.id, analysis.url, image, reader, folder)
    return crud.get_recipe(session, created.id)


WEBSITE_TEXT_CUT = Issue(
    kind="other",
    message="הדף ארוך, ולכן נקראו רק 20,000 התווים הראשונים של הטקסט שלו. השוו לדף ובדקו שלא חסר דבר.",
)


def _structured_draft(
    recipe: StructuredRecipe, original: str, use_model: bool, session: Session, new_extractor: ExtractorFactory
) -> tuple[RecipeInput, str | None]:
    """The draft from the page's recipe data, and the model that chose its category (None: none did).
    A model that cannot be reached or answers badly leaves the draft unclassified, never unsaved."""
    categories = crud.list_categories(session)
    session.commit()  # end the read before the call to the model
    if not use_model:
        return structured_draft(recipe, original, categories, None, "המתכון יובא בלי מודל, ולכן לא סווג. בחרו קטגוריה קיימת, או השאירו לא מסווג."), None
    unanswered = "המודל לא ענה על הקטגוריה, ולכן המתכון לא סווג. בחרו קטגוריה קיימת, או השאירו לא מסווג."
    try:
        extractor = new_extractor()
        classify = getattr(extractor, "classify_draft", None)
        if classify is None:
            return structured_draft(recipe, original, categories, None, unanswered), None
        classification = classify(structured_draft(recipe, original, categories, None), categories)
    except Exception:  # noqa: BLE001  the recipe itself is complete: only its category is missing
        log.exception("Classifying the recipe from %s failed", recipe.title)
        return structured_draft(recipe, original, categories, None, unanswered), None
    return structured_draft(recipe, original, categories, classification), extractor.model


def _attach_website_image(session: Session, recipe_id: int, page_url: str, image_url: str, reader: WebReader, folder: Path) -> None:
    """The page's main picture, saved with the new draft. A problem with it never fails the import: the
    draft is saved already, and a review point says the picture is missing."""
    try:
        data = reader.image(image_url)
        media.attach_website_image(session, folder, crud.load_recipe(session, recipe_id), page_url, data)
        issue = None
    except WebsiteError as error:
        log.info("The picture %s of %s was not saved: %s", image_url, page_url, error.message)
        session.rollback()
        issue = Issue(kind="media_incomplete", message="התמונה הראשית של המתכון לא נשמרה: האתר לא שלח אותה. אפשר להעלות תמונה בעצמכם.")
    except Exception:  # noqa: BLE001  any failure here must leave the saved draft as it is
        log.exception("Saving the picture %s of %s failed", image_url, page_url)
        session.rollback()
        issue = Issue(kind="media_incomplete", message="התמונה הראשית של המתכון לא נשמרה. אפשר להעלות תמונה בעצמכם.")
    if issue is not None:
        crud.add_issue(session, recipe_id, issue)
    session.expire_all()


def _attach_media(
    session: Session, recipe_id: int, ref: InstagramRef, retrieval: CaptionRetrieval, folder: Path,
    transport: httpx2.BaseTransport | None,
) -> None:
    """The post's pictures and videos, saved here with the new draft. A problem with them never fails the
    import: the draft is saved already, and a review point says what is missing."""
    try:
        report = media.attach_post_media(session, folder, crud.load_recipe(session, recipe_id), ref, retrieval.media, transport)
        issue = media.report_issue(report)
    except Exception:  # noqa: BLE001  any failure here must leave the saved draft as it is
        log.exception("Saving the media of %s failed", ref.canonical_url)
        session.rollback()
        issue = Issue(kind="media_incomplete", message='שמירת התמונות והסרטונים של הפוסט נכשלה. אפשר לנסות שוב בכפתור "שליפת מדיה מהפוסט".')
    if issue is not None:
        crud.add_issue(session, recipe_id, issue)
    session.expire_all()


def recipes_with_post(session: Session, url: str) -> list[LinkedRecipe]:
    """The recipes that already link to this post or page, in their imported original or their sources.
    An Instagram post whatever the address's form: /p/, /reel/ or /tv/, with or without a username or
    tracking parameters (the shortcode decides). A website's page with or without "www.", a final "/"
    or tracking parameters (website.page_key)."""
    found: dict[int, LinkedRecipe] = {}
    if website.is_instagram(url):
        wanted = parse_instagram_url(url).shortcode
        for recipe, linked in crud.linked_urls(session):
            try:
                if parse_instagram_url(linked).shortcode == wanted:
                    found.setdefault(recipe.id, recipe)
            except InvalidInstagramUrl:
                continue  # a website or another kind of address: not this post
        return list(found.values())
    wanted_page = website.page_key(url)
    for recipe, linked in crud.linked_urls(session):
        if not website.is_instagram(linked) and website.page_key(linked) == wanted_page:
            found.setdefault(recipe.id, recipe)
    return list(found.values())


def _refuse_duplicate(session: Session, url: str) -> None:
    """Stop before reading anything when the post is already in the notebook: the page shows the
    recipes and lets the person open one or import another copy (allow_duplicate)."""
    matches = recipes_with_post(session, url)
    if matches:
        raise ApiError(
            409, "duplicate_link", "This post is already in the notebook.",
            {"url": url, "matches": [match.model_dump(mode="json") for match in matches]},
        )


def _canonical_url(text: str) -> str:
    try:
        return parse_instagram_url(text).canonical_url
    except InvalidInstagramUrl as error:
        raise ApiError(422, "invalid_instagram_url", str(error)) from None


def _link_url(text: str) -> str:
    """A link kept with pasted text: an Instagram post's canonical address, or a checked website address
    (nothing is fetched)."""
    if website.is_instagram(text):
        return _canonical_url(text)
    try:
        return website.check_url(text)
    except WebsiteError as error:
        raise _website_error(error, text.strip()) from None


def _draft(
    text: str, use_model: bool, session: Session, new_extractor: ExtractorFactory
) -> tuple[RecipeInput, str | None]:
    """The draft for a text, and the model that read it (None: saved without a model, to fill in by hand)."""
    if not use_model:
        return manual_draft(text), None
    extractor = new_extractor()
    categories = crud.list_categories(session)
    # End the read before the long call to the model, so the database is not held while we wait.
    session.commit()
    output = extractor.extract(text, categories)
    if not is_recipe(output):
        raise ApiError(422, "not_a_recipe", "The model found no recipe in this text.")
    return make_draft(output, text, categories), extractor.model
