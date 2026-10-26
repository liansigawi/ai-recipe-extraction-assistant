"""Categories: the list for the pickers and the filters, and creating and editing them.

    GET  /api/categories        top-level categories, each with its subcategories
    POST /api/categories        a new category, or with parent_id a subcategory of a top-level one
    PUT  /api/categories/{id}   a new name and description (the id, the parent and the recipes stay)

Only the person creates categories, here. Nothing else in the backend ever does: the model can only
choose among existing ids. The descriptions are what the model classifies by at the next import.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.errors import ERROR_RESPONSES, ErrorResponse
from app.schemas import Category, CategoryInput, CategoryRow, CategoryUpdate

router = APIRouter(prefix="/api/categories", tags=["categories"])
SessionDep = Annotated[Session, Depends(get_session)]
CHANGE_ERRORS = {**ERROR_RESPONSES, 409: {"model": ErrorResponse, "description": "The name is taken at that level"}}


@router.get("")
def list_categories(session: SessionDep) -> list[Category]:
    """Top-level categories, each with its subcategories."""
    return crud.list_categories(session)


@router.post("", status_code=status.HTTP_201_CREATED, responses=CHANGE_ERRORS)
def create_category(data: CategoryInput, session: SessionDep) -> CategoryRow:
    """A new top-level category, or a subcategory of an existing top-level category (one level deep)."""
    return crud.create_category(session, data)


@router.put("/{category_id}", responses=CHANGE_ERRORS)
def update_category(category_id: int, data: CategoryUpdate, session: SessionDep) -> CategoryRow:
    """Rename a category or change its description. Its id, parent and recipes stay as they are."""
    return crud.update_category(session, category_id, data)
