"""Create, read, update and delete recipes; list categories.

The API routes (app/api/) call these functions. They convert between the database rows
(app/models.py) and the contract (app/schemas.py), and enforce the category rule before
anything is written. Comments show the SQL that SQLAlchemy sends for each operation;
run with RECIPES_SQL_ECHO=true to see it live.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.db import utc_now
from app.errors import ApiError

# --- Reading -------------------------------------------------------------------------------


def to_schema(row: models.Recipe) -> schemas.Recipe:
    """A database row -> the contract the API returns (validated on the way out)."""
    return schemas.Recipe(
        id=row.id,
        title=row.title,
        category=schemas.CategoryRef(id=row.category.id, name=row.category.name) if row.category else None,
        subcategory=schemas.CategoryRef(id=row.subcategory.id, name=row.subcategory.name) if row.subcategory else None,
        servings=row.servings,
        ingredient_groups=row.ingredient_groups,
        step_groups=row.step_groups,
        notes=row.notes,
        sources=[schemas.Source(kind=s.kind, url=s.url, creators=s.creators) for s in row.sources],
        is_sample=row.is_sample,
        status=row.status,
        issues=row.issues,
        original=(
            schemas.ImportedOriginal(
                kind=row.original.kind,
                text=row.original.original_text,
                model=row.original.model,
                imported_at=row.original.imported_at,
            )
            if row.original
            else None
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _recipe_query():
    # SELECT ... FROM recipes ORDER BY recipes.id DESC   (newest first)
    # selectinload: fetch all their sources and categories in one extra query each
    # ("SELECT ... FROM recipe_sources WHERE recipe_id IN (...)"), not one query per recipe.
    return (
        select(models.Recipe)
        .options(
            selectinload(models.Recipe.sources),
            selectinload(models.Recipe.category),
            selectinload(models.Recipe.subcategory),
            selectinload(models.Recipe.original),
        )
        .order_by(models.Recipe.id.desc())
    )


def list_recipes(session: Session) -> list[schemas.Recipe]:
    return [to_schema(row) for row in session.scalars(_recipe_query())]


def _load(session: Session, recipe_id: int) -> models.Recipe:
    # SELECT ... FROM recipes WHERE recipes.id = ?
    row = session.scalars(_recipe_query().where(models.Recipe.id == recipe_id)).one_or_none()
    if row is None:
        raise ApiError(404, "recipe_not_found", f"There is no recipe with id {recipe_id}.")
    return row


def get_recipe(session: Session, recipe_id: int) -> schemas.Recipe:
    return to_schema(_load(session, recipe_id))


def list_categories(session: Session) -> list[schemas.Category]:
    # SELECT ... FROM categories WHERE parent_id IS NULL ORDER BY id   (+ their subcategories)
    rows = session.scalars(
        select(models.Category)
        .where(models.Category.parent_id.is_(None))
        .options(selectinload(models.Category.subcategories))
        .order_by(models.Category.id)
    )
    return [
        schemas.Category(
            id=row.id,
            name=row.name,
            description=row.description,
            subcategories=[schemas.Subcategory(id=s.id, name=s.name, description=s.description) for s in row.subcategories],
        )
        for row in rows
    ]


# --- The category rule -------------------------------------------------------------------------


def check_classification(session: Session, category_id: int | None, subcategory_id: int | None) -> None:
    """Category ids must name existing rows, and the subcategory must belong to the category.

    Nothing here ever creates a category. (The database enforces the parent pair too;
    checking first gives a clear error message instead of a database error.)
    """
    if category_id is None:
        return  # unclassified is allowed
    category = session.get(models.Category, category_id)  # SELECT ... FROM categories WHERE id = ?
    if category is None or category.parent_id is not None:
        raise ApiError(
            422, "unknown_category", f"There is no top-level category with id {category_id}.",
            {"field": "category_id"},
        )
    if subcategory_id is None:
        return
    subcategory = session.get(models.Category, subcategory_id)
    if subcategory is None or subcategory.parent_id != category_id:
        raise ApiError(
            422, "subcategory_not_in_category",
            f"Category {category_id} has no subcategory with id {subcategory_id}.",
            {"field": "subcategory_id"},
        )


# --- Writing ---------------------------------------------------------------------------------------


def _apply(row: models.Recipe, data: schemas.RecipeInput) -> None:
    """Copy the editable fields from the input onto a row."""
    row.title = data.title
    row.category_id = data.category_id
    row.subcategory_id = data.subcategory_id
    row.servings = data.servings
    # Plain lists and dicts go into the JSON columns, in order.
    row.ingredient_groups = [group.model_dump() for group in data.ingredient_groups]
    row.step_groups = [group.model_dump() for group in data.step_groups]
    row.notes = list(data.notes)
    # Replacing the list: removed sources are deleted (delete-orphan), new ones inserted.
    row.sources = [
        models.RecipeSource(position=index, kind=source.kind, url=source.url, creators=list(source.creators))
        for index, source in enumerate(data.sources)
    ]
    row.status = data.status
    row.issues = [issue.model_dump() for issue in data.issues]
    # row.original is deliberately not touched: the imported text never changes after import.


def create_recipe(session: Session, data: schemas.RecipeInput, *, is_sample: bool = False) -> schemas.Recipe:
    check_classification(session, data.category_id, data.subcategory_id)
    now = utc_now()
    row = models.Recipe(is_sample=is_sample, created_at=now, updated_at=now)
    _apply(row, data)
    session.add(row)
    # INSERT INTO recipes (...) VALUES (...); INSERT INTO recipe_sources (...) VALUES (...); COMMIT
    session.commit()
    return get_recipe(session, row.id)


def create_import(
    session: Session, draft: schemas.RecipeInput, *, original_text: str, model: str | None
) -> schemas.Recipe:
    """Save an imported draft together with the text it came from, in one transaction."""
    check_classification(session, draft.category_id, draft.subcategory_id)
    now = utc_now()
    row = models.Recipe(created_at=now, updated_at=now)
    _apply(row, draft)
    row.original = models.RecipeImport(kind="text", original_text=original_text, model=model, imported_at=now)
    session.add(row)
    # INSERT INTO recipes ...; INSERT INTO recipe_sources ...; INSERT INTO recipe_imports ...; COMMIT
    session.commit()
    return get_recipe(session, row.id)


def update_recipe(session: Session, recipe_id: int, data: schemas.RecipeInput) -> schemas.Recipe:
    row = _load(session, recipe_id)
    check_classification(session, data.category_id, data.subcategory_id)
    _apply(row, data)
    row.updated_at = utc_now()
    # UPDATE recipes SET ... WHERE id = ?; DELETE/INSERT recipe_sources ...; COMMIT
    session.commit()
    session.expire(row)  # reload the category names after a category change
    return get_recipe(session, recipe_id)


def delete_recipe(session: Session, recipe_id: int) -> None:
    row = _load(session, recipe_id)
    session.delete(row)
    # DELETE FROM recipe_sources WHERE recipe_id = ?; DELETE FROM recipe_imports WHERE id = ?;
    # DELETE FROM recipes WHERE id = ?; COMMIT
    session.commit()
