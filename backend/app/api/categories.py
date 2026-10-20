"""Category endpoint (read-only for now): the editor's category picker uses it.

Creating and editing categories is a deliberate user action that arrives with the
category settings screen (milestone 6). Nothing in the backend creates categories
on its own.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session
from app.schemas import Category

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
def list_categories(session: Annotated[Session, Depends(get_session)]) -> list[Category]:
    """Top-level categories, each with its subcategories."""
    return crud.list_categories(session)
