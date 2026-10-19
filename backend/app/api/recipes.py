"""Recipe endpoints.

Milestone 2: read-only, serving the sample recipes from app/sample_data.py.
Milestone 3 replaces the sample list with the SQLite database and adds editing.
"""

from typing import Annotated

from fastapi import APIRouter, Path

from app.errors import ERROR_RESPONSES, ApiError
from app.sample_data import SAMPLE_RECIPES
from app.schemas import Recipe

router = APIRouter(prefix="/api/recipes", tags=["recipes"], responses=ERROR_RESPONSES)

# Ids are positive and fit in SQLite's 64-bit integers; anything else is a 422 in the error format.
RecipeId = Annotated[int, Path(ge=1, le=2**63 - 1)]


# The return type annotation is also the response model: FastAPI validates the
# data against it and documents it at /docs.
@router.get("")
def list_recipes() -> list[Recipe]:
    """All recipes. Milestone 2: the four built-in sample recipes; nothing is saved yet."""
    return SAMPLE_RECIPES


@router.get("/{recipe_id}")
def get_recipe(recipe_id: RecipeId) -> Recipe:
    """One recipe by id. Milestone 2: one of the built-in sample recipes."""
    for recipe in SAMPLE_RECIPES:
        if recipe.id == recipe_id:
            return recipe
    raise ApiError(404, "recipe_not_found", f"There is no recipe with id {recipe_id}.")
