"""Importing pasted text: a model reads it, the backend checks the answer, a draft is saved.

    GET  /api/extraction     can imports use the model right now, and which one?
    POST /api/imports/text   pasted text -> a saved draft (status "draft") with review issues

The model is Claude or a local model through Ollama (RECIPES_EXTRACTOR, app/extraction/choose.py).
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
from app.extraction.choose import extraction_info as current_extraction_info
from app.extraction.choose import make_extractor
from app.extraction.claude import Extractor
from app.extraction.review import is_recipe, make_draft, manual_draft
from app.schemas import ExtractionInfo, Recipe, TextImport

IMPORT_ERRORS = {
    **ERROR_RESPONSES,
    502: {"model": ErrorResponse, "description": "The model failed or gave an unusable answer"},
    503: {"model": ErrorResponse, "description": "No API key, Ollama not running, or the model is busy"},
    504: {"model": ErrorResponse, "description": "The model did not answer in time"},
}

router = APIRouter(prefix="/api", tags=["imports"])

SessionDep = Annotated[Session, Depends(get_session)]
ExtractorFactory = Callable[[], Extractor]


def get_extractor_factory() -> ExtractorFactory:
    """FastAPI dependency: how to get an extractor. Tests replace it with a stand-in.

    Settings are read when an import starts, so a key or a model choice added to .env works
    without restarting the backend.
    """
    return lambda: make_extractor(load_settings())


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
    """
    if not data.use_model:
        return crud.create_import(session, manual_draft(data.text), original_text=data.text, model=None)

    extractor = new_extractor()
    categories = crud.list_categories(session)
    # End the read before the long call to the model, so the database is not held while we wait.
    session.commit()
    output = extractor.extract(data.text, categories)
    if not is_recipe(output):
        raise ApiError(422, "not_a_recipe", "The model found no recipe in this text.")
    draft = make_draft(output, data.text, categories)
    return crud.create_import(session, draft, original_text=data.text, model=extractor.model)
