"""Importing pasted text: Claude reads it, the backend checks the answer, a draft is saved.

    GET  /api/extraction     can imports use Claude right now (is an API key set)?
    POST /api/imports/text   pasted text -> a saved draft (status "draft") with review issues

The draft is saved at once, together with the original text, so nothing is lost; the person
then reviews it in the editor and saves it explicitly. If anything fails before that,
nothing is saved and the page keeps the pasted text.
"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud
from app.config import load_settings
from app.db import get_session
from app.errors import ERROR_RESPONSES, ApiError, ErrorResponse
from app.extraction.claude import ClaudeExtractor, Extractor
from app.extraction.review import build_draft, manual_draft
from app.schemas import ExtractionInfo, Recipe, TextImport

IMPORT_ERRORS = {
    **ERROR_RESPONSES,
    502: {"model": ErrorResponse, "description": "The Claude API failed or gave an unusable answer"},
    503: {"model": ErrorResponse, "description": "No API key is configured, or the Claude API is busy"},
    504: {"model": ErrorResponse, "description": "The Claude API did not answer in time"},
}

router = APIRouter(prefix="/api", tags=["imports"])

SessionDep = Annotated[Session, Depends(get_session)]
ExtractorFactory = Callable[[], Extractor]


def get_extractor_factory() -> ExtractorFactory:
    """FastAPI dependency: how to get an extractor. Tests replace it with a stand-in.

    Settings are read when an import starts, so an API key added to .env works without
    restarting the backend.
    """

    def make() -> Extractor:
        settings = load_settings()
        if settings.anthropic_api_key is None or not settings.extraction_configured:
            raise ApiError(
                503,
                "extraction_not_configured",
                "No Anthropic API key is configured on the backend. See the README, section 'Connect the Claude API'.",
            )
        return ClaudeExtractor(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.model,
            timeout=settings.model_timeout_seconds,
        )

    return make


@router.get("/extraction")
def extraction_info() -> ExtractionInfo:
    """Whether imports can use Claude now, and which model they use. Never returns the key itself."""
    settings = load_settings()
    return ExtractionInfo(configured=settings.extraction_configured, model=settings.model)


@router.post("/imports/text", status_code=status.HTTP_201_CREATED, responses=IMPORT_ERRORS)
def import_text(
    data: TextImport,
    session: SessionDep,
    make_extractor: Annotated[ExtractorFactory, Depends(get_extractor_factory)],
) -> Recipe:
    """Pasted text -> a saved draft for review, with the original text kept beside it.

    With use_model = false, the text is saved as a draft without Claude, to fill in by hand.
    """
    if not data.use_model:
        return crud.create_import(session, manual_draft(data.text), original_text=data.text, model=None)

    extractor = make_extractor()
    categories = crud.list_categories(session)
    # End the read before the long call to Claude, so the database is not held while we wait.
    session.commit()
    output = extractor.extract(data.text, categories)
    if not output.is_recipe:
        raise ApiError(422, "not_a_recipe", "Claude found no recipe in this text.")
    draft = build_draft(output, data.text, categories)
    return crud.create_import(session, draft, original_text=data.text, model=extractor.model)
