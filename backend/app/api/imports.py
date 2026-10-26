"""Importing a recipe: a model reads the text, the backend checks the answer, a draft is saved.

    GET  /api/extraction          can imports use the model right now, and which one?
    POST /api/imports/text        pasted text -> a saved draft (status "draft") with review issues
    POST /api/imports/instagram   a post's address -> its caption, read from Instagram -> a saved draft

The model is Claude or a local model through Ollama (RECIPES_EXTRACTOR, app/extraction/choose.py).
The draft is saved at once, together with the original text, so nothing is lost; the person
then reviews it in the editor and saves it explicitly. If anything fails before that,
nothing is saved and the page keeps the pasted text.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import httpx2

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud, media
from app.config import load_settings
from app.db import get_session
from app.errors import ERROR_RESPONSES, ApiError, ErrorResponse
from app.extraction.choose import extraction_info as current_extraction_info
from app.extraction.choose import make_extractor
from app.extraction.claude import Extractor
from app.extraction.review import is_recipe, make_draft, manual_draft
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

router = APIRouter(prefix="/api", tags=["imports"])
log = logging.getLogger("uvicorn.error")

SessionDep = Annotated[Session, Depends(get_session)]
ExtractorFactory = Callable[[], Extractor]


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


@router.get("/extraction")
def extraction_info() -> ExtractionInfo:
    """Whether imports can use the model now, which one, and whether the text stays on this computer.

    Never returns the API key itself.
    """
    return current_extraction_info(load_settings())


@router.post("/imports/text", status_code=status.HTTP_201_CREATED, responses=IMPORT_ERRORS)
def import_text(
    data: TextImport,
    session: SessionDep,
    new_extractor: Annotated[ExtractorFactory, Depends(get_extractor_factory)],
) -> Recipe:
    """Pasted text -> a saved draft for review, with the original text kept beside it.

    With use_model = false, the text is saved as a draft without a model, to fill in by hand.
    With a url (the Instagram post the text was copied from, after reading the post failed), the
    address is kept with the original and becomes the recipe's source.
    """
    url = _canonical_url(data.url) if data.url is not None and data.url.strip() else None
    if url is not None and not data.allow_duplicate:
        _refuse_duplicate(session, url)
    draft, model = _draft(data.text, data.use_model, session, new_extractor)
    if url is not None:
        draft = draft.model_copy(update={"sources": [Source(kind="instagram", url=url)]})
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
        raise ApiError(error.status_code, error.code, error.message, details) from None
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
    """The recipes that already link to this post, in their imported original or their sources. The
    same post whatever the address's form: /p/, /reel/ or /tv/, with or without a username or tracking
    parameters (the shortcode decides)."""
    wanted = parse_instagram_url(url).shortcode
    found: dict[int, LinkedRecipe] = {}
    for recipe, linked in crud.linked_urls(session):
        try:
            if parse_instagram_url(linked).shortcode == wanted:
                found.setdefault(recipe.id, recipe)
        except InvalidInstagramUrl:
            continue  # a website or another kind of address: not this post
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
