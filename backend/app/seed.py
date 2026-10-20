"""Prepare the database at start-up.

- Every start: create any missing tables (CREATE TABLE ... for tables that do not exist yet).
- Only for a brand-new database file: add the starter categories and the sample recipes.
  So samples you delete stay deleted, and your recipes are never touched.
"""

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import crud, models
from app.db import Base
from app.sample_data import SAMPLE_RECIPES, STARTER_CATEGORIES


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def seed_new_database(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids: dict[str, int] = {}
        for name, description in STARTER_CATEGORIES:
            row = models.Category(name=name, description=description)
            session.add(row)
            session.flush()  # INSERT now, so SQLite assigns row.id
            ids[name] = row.id
        session.commit()

        # Newest recipes are listed first, so insert the samples in reverse to show them in file order.
        for category_name, recipe in reversed(SAMPLE_RECIPES):
            category_id = ids[category_name] if category_name is not None else None
            crud.create_recipe(session, recipe.model_copy(update={"category_id": category_id}), is_sample=True)
