"""Fill a brand-new database with the starter categories and the sample recipes.

Called only when app/migrate.py has just created the tables, so samples you delete stay
deleted, and your recipes are never touched.
"""

from sqlalchemy.orm import Session, sessionmaker

from app import crud, models
from app.sample_data import ADDED_CATEGORIES, SAMPLE_RECIPES, STARTER_CATEGORIES, STARTER_SUBCATEGORIES


def seed_new_database(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        ids: dict[str, int] = {}
        for name, description in STARTER_CATEGORIES:
            row = models.Category(name=name, description=description)
            session.add(row)
            session.flush()  # INSERT now, so SQLite assigns row.id
            ids[name] = row.id
        for parent, subcategories in STARTER_SUBCATEGORIES.items():
            for name, description in subcategories:
                session.add(models.Category(name=name, description=description, parent_id=ids[parent]))
                session.flush()  # in order: the same ids as in a database that migration 0007 upgraded
        for name, description in ADDED_CATEGORIES:
            session.add(models.Category(name=name, description=description))
            session.flush()  # after the subcategories: the same ids as in a database that migration 0012 upgraded
        session.commit()

        # Newest recipes are listed first, so insert the samples in reverse to show them in file order.
        for category_name, recipe in reversed(SAMPLE_RECIPES):
            category_id = ids[category_name] if category_name is not None else None
            crud.create_recipe(session, recipe.model_copy(update={"category_id": category_id}), is_sample=True)
