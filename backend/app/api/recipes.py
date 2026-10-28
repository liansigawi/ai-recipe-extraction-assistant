"""Recipe endpoints: list, read, create, save (update), mark as cooked, and delete.

Each route is a thin layer: FastAPI validates the input against the contract
(app/schemas.py), gives the route a database session, and the route calls app/crud.py.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app import crud, media
from app.db import get_session
from app.errors import ERROR_RESPONSES
from app.schemas import CookedChoice, Recipe, RecipeInput

router = APIRouter(prefix="/api/recipes", tags=["recipes"], responses=ERROR_RESPONSES)

# Ids are positive and fit in SQLite's 64-bit integers; anything else is a 422 in the error format.
RecipeId = Annotated[int, Path(ge=1, le=2**63 - 1)]
# Depends(get_session): FastAPI calls get_session for each request and passes the session in.
SessionDep = Annotated[Session, Depends(get_session)]


# The return type annotation is also the response model: FastAPI validates the
# data against it and documents it at /docs.
@router.get("")
def list_recipes(session: SessionDep) -> list[Recipe]:
    """All recipes, newest first."""
    return crud.list_recipes(session)


@router.get("/{recipe_id}")
def get_recipe(recipe_id: RecipeId, session: SessionDep) -> Recipe:
    """One recipe by id."""
    return crud.get_recipe(session, recipe_id)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_recipe(data: RecipeInput, session: SessionDep) -> Recipe:
    """Create a recipe. Returns it with its new id and timestamps."""
    return crud.create_recipe(session, data)


@router.put("/{recipe_id}")
def update_recipe(recipe_id: RecipeId, data: RecipeInput, session: SessionDep) -> Recipe:
    """Save a recipe: replaces all its editable fields with the ones sent."""
    return crud.update_recipe(session, recipe_id, data)


@router.put("/{recipe_id}/cooked")
def set_cooked(recipe_id: RecipeId, data: CookedChoice, session: SessionDep) -> Recipe:
    """Mark a recipe as cooked (true) or not yet (false). Nothing else about it changes."""
    return crud.set_cooked(session, recipe_id, data.cooked)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: RecipeId, session: SessionDep) -> Response:
    """Delete a recipe with its sources, original and media. Its media files are deleted unless another
    recipe uses them."""
    crud.delete_recipe(session, recipe_id)
    media.collect_garbage(session, media.get_media_root())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
