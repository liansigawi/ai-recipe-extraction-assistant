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
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud
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
from app.schemas import ExtractionInfo, InstagramImport, Issue, Recipe, RecipeInput, Source, TextImport

IMPORT_ERRORS = {
    **ERROR_RESPONSES,
    502: {"model": ErrorResponse, "description": "The model failed or gave an unusable answer"},
    503: {"model": ErrorResponse, "description": "No API key, Ollama not running, or the model is busy"},
    504: {"model": ErrorResponse, "description": "The model did not answer in time"},
}

INSTAGRAM_ERRORS = {
    **IMPORT_ERRORS,
    409: {"model": ErrorResponse, "description": "Only a preview of the caption was read; it may be cut off"},
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
) -> Recipe:
    """A public post's address -> its caption, read from Instagram -> a saved draft, as for pasted text.

    The full caption and the post's address are kept with the original; the address is also the
    recipe's (editable) source, with the post's author and co-authors. Nothing is saved when the post
    cannot be read or only a preview of its caption was found: the error says why, and its details
    carry the address and any caption read, so the page can offer pasting the caption instead.
    """
    url = _canonical_url(data.url)
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
    creators = [name for name in (retrieval.username, *retrieval.coauthors) if name]
    draft = draft.model_copy(update={"sources": [Source(kind="instagram", url=url, creators=creators)]})
    return crud.create_import(
        session, draft, original_text=retrieval.caption, model=model, kind="instagram", url=url,
        retrieved_from=retrieval.retrieved_from,
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
