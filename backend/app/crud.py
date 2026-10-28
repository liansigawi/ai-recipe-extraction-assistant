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
        cooked=row.cooked,
        original=(
            schemas.ImportedOriginal(
                kind=row.original.kind,
                text=row.original.original_text,
                model=row.original.model,
                imported_at=row.original.imported_at,
                url=row.original.url,
                retrieved_from=row.original.retrieved_from,
                author=(row.original.source_details or {}).get("author"),
                coauthors=(row.original.source_details or {}).get("coauthors", []),
                site_name=(row.original.source_details or {}).get("site_name"),
            )
            if row.original
            else None
        ),
        media=(media := [_media_item(m) for m in ordered_media(row)]),
        cover_id=next((m.id for m in media if m.is_cover), next((m.id for m in media if _has_picture(m)), None)),
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
            selectinload(models.Recipe.media).selectinload(models.RecipeMedia.file),
            selectinload(models.Recipe.media).selectinload(models.RecipeMedia.thumbnail),
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


def ordered_media(row: models.Recipe) -> list[models.RecipeMedia]:
    """The post's items in the post's order first, then uploads in the order they came."""
    return sorted(row.media, key=lambda m: (m.post_index is None, m.post_shortcode or "", m.post_index or 0, m.id))


def _file_ref(file: models.MediaFile | None) -> schemas.MediaFileRef | None:
    if file is None:
        return None
    return schemas.MediaFileRef(id=file.id, url=f"/api/media/{file.id}", content_type=file.content_type, size_bytes=file.size_bytes)


def _media_item(m: models.RecipeMedia) -> schemas.RecipeMediaItem:
    return schemas.RecipeMediaItem(
        id=m.id, kind=m.kind, status=m.status, file=_file_ref(m.file), thumbnail=_file_ref(m.thumbnail),
        origin=m.origin, post_url=m.post_url, post_index=m.post_index, width=m.width, height=m.height,
        is_cover=m.is_cover,
    )


def _has_picture(m: schemas.RecipeMediaItem) -> bool:
    return (m.kind == "image" and m.file is not None) or m.thumbnail is not None


def add_issue(session: Session, recipe_id: int, issue: schemas.Issue) -> None:
    """A review point added after the import (about its media), first in the list."""
    row = _load(session, recipe_id)
    row.issues = [issue.model_dump(mode="json"), *row.issues]  # a new list: the JSON column notices the change
    session.commit()


def load_recipe(session: Session, recipe_id: int) -> models.Recipe:
    """The recipe row with its media, for the media endpoints (404 if there is none)."""
    return _load(session, recipe_id)


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


def create_category(session: Session, data: schemas.CategoryInput) -> schemas.CategoryRow:
    """A category the person creates: top-level, or a subcategory of an existing top-level category
    (one level deep). Its name must be new among its siblings."""
    if data.parent_id is not None:
        parent = session.get(models.Category, data.parent_id)
        if parent is None or parent.parent_id is not None:
            raise ApiError(
                422, "invalid_parent", f"There is no top-level category with id {data.parent_id} to add a subcategory to.",
                {"field": "parent_id"},
            )
    _check_name_free(session, data.name, data.parent_id, None)
    row = models.Category(name=data.name, description=data.description, parent_id=data.parent_id)
    session.add(row)
    session.commit()  # INSERT INTO categories ...; COMMIT
    return _category_row(row)


def update_category(session: Session, category_id: int, data: schemas.CategoryUpdate) -> schemas.CategoryRow:
    """A new name and description; the id stays, so every recipe in it stays in it."""
    row = session.get(models.Category, category_id)
    if row is None:
        raise ApiError(404, "category_not_found", f"There is no category with id {category_id}.")
    _check_name_free(session, data.name, row.parent_id, row.id)
    row.name, row.description = data.name, data.description
    session.commit()  # UPDATE categories SET name = ?, description = ? WHERE id = ?; COMMIT
    return _category_row(row)


def _check_name_free(session: Session, name: str, parent_id: int | None, own_id: int | None) -> None:
    same_level = models.Category.parent_id.is_(None) if parent_id is None else models.Category.parent_id == parent_id
    taken = {row.name.casefold(): row.id for row in session.scalars(select(models.Category).where(same_level))}
    if taken.get(name.casefold(), own_id) != own_id:
        where = "among the top-level categories" if parent_id is None else "in this category"
        raise ApiError(409, "category_name_taken", f'There is already a category named "{name}" {where}.', {"field": "name"})


def _category_row(row: models.Category) -> schemas.CategoryRow:
    return schemas.CategoryRow(id=row.id, name=row.name, description=row.description, parent_id=row.parent_id)


def linked_urls(session: Session) -> list[tuple[schemas.LinkedRecipe, str]]:
    """Every address a recipe holds, in its imported original or its sources, with the recipe: drafts
    and saved recipes alike. (Which of them are the same post is decided by the caller.)"""
    recipe = (models.Recipe.id, models.Recipe.title, models.Recipe.status)
    originals = select(*recipe, models.RecipeImport.url).join(models.RecipeImport).where(models.RecipeImport.url.is_not(None))
    sources = select(*recipe, models.RecipeSource.url).join(models.RecipeSource).where(models.RecipeSource.url.is_not(None))
    # SELECT ... FROM recipes JOIN recipe_imports ... UNION ALL SELECT ... FROM recipes JOIN recipe_sources ...
    rows = sorted(session.execute(originals.union_all(sources)), key=lambda row: row[0], reverse=True)  # newest first
    return [(schemas.LinkedRecipe(id=id_, title=title, status=status), url) for id_, title, status, url in rows]


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
        models.RecipeSource(
            position=index, kind=source.kind, url=source.url, creators=[c.model_dump() for c in source.creators]
        )
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
    session: Session,
    draft: schemas.RecipeInput,
    *,
    original_text: str,
    model: str | None,
    kind: schemas.ImportKind = "text",
    url: str | None = None,
    retrieved_from: schemas.RetrievedFrom | None = None,
    source_details: dict | None = None,
) -> schemas.Recipe:
    """Save an imported draft together with the text it came from (and the post's address), in one transaction."""
    check_classification(session, draft.category_id, draft.subcategory_id)
    now = utc_now()
    row = models.Recipe(created_at=now, updated_at=now)
    _apply(row, draft)
    row.original = models.RecipeImport(
        kind=kind, original_text=original_text, model=model, imported_at=now, url=url,
        retrieved_from=retrieved_from, source_details=source_details,
    )
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


def set_cooked(session: Session, recipe_id: int, cooked: bool) -> schemas.Recipe:
    """Mark a recipe as cooked, or not yet. Its content and "updated" time stay as they are: this is
    about you, not an edit of the recipe."""
    row = _load(session, recipe_id)
    row.cooked = cooked
    # UPDATE recipes SET cooked = ? WHERE id = ?; COMMIT
    session.commit()
    return get_recipe(session, recipe_id)


def delete_recipe(session: Session, recipe_id: int) -> None:
    row = _load(session, recipe_id)
    session.delete(row)
    # DELETE FROM recipe_sources WHERE recipe_id = ?; DELETE FROM recipe_imports WHERE id = ?;
    # DELETE FROM recipes WHERE id = ?; COMMIT
    session.commit()
