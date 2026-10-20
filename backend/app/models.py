"""The database tables, as SQLAlchemy classes. Each class is a table; each attribute is a column.

    categories        id, name, description, parent_id (NULL = top level)
    recipes           id, title, category_id, subcategory_id, servings,
                      ingredient_groups (JSON), step_groups (JSON), notes (JSON),
                      is_sample, created_at, updated_at
    recipe_sources    id, recipe_id, position, kind, url, creators (JSON)

Relationships:
- a subcategory is a category row whose parent_id points at a top-level category;
- a recipe points at a category and, optionally, one of its subcategories;
- a recipe has an ordered list of sources (one-to-many); deleting the recipe deletes them.

Ordered recipe content (ingredient groups, step groups, notes) lives in JSON columns:
a recipe is always loaded and saved as a whole, so its lists need no tables of their own.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


class Category(Base):
    __tablename__ = "categories"
    # (id, parent_id) is unique, so recipes can point at the *pair* (see Recipe below).
    __table_args__ = (UniqueConstraint("id", "parent_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)  # assigned by SQLite: 1, 2, 3...
    name: Mapped[str]  # Mapped[str]: NOT NULL; Mapped[str | None]: may be NULL
    description: Mapped[str | None]
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    subcategories: Mapped[list["Category"]] = relationship(order_by="Category.id")


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (
        # The database itself refuses a subcategory under the wrong category: the pair
        # (subcategory_id, category_id) must match a row's (id, parent_id) in categories.
        ForeignKeyConstraint(["subcategory_id", "category_id"], ["categories.id", "categories.parent_id"]),
        # ...and a subcategory without a category (a pair with a NULL is not checked by the key above).
        CheckConstraint("subcategory_id IS NULL OR category_id IS NOT NULL", name="subcategory_needs_category"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    subcategory_id: Mapped[int | None]
    servings: Mapped[str | None]
    ingredient_groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    step_groups: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    notes: Mapped[list[str]] = mapped_column(JSON)
    is_sample: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)

    # Read-only shortcuts to the category rows (the ids above are what we write).
    category: Mapped[Category | None] = relationship(
        primaryjoin="Recipe.category_id == Category.id", foreign_keys="Recipe.category_id", viewonly=True
    )
    subcategory: Mapped[Category | None] = relationship(
        primaryjoin="Recipe.subcategory_id == Category.id", foreign_keys="Recipe.subcategory_id", viewonly=True
    )
    # cascade="all, delete-orphan": sources are saved and deleted together with their recipe,
    # and a source removed from this list is deleted from the table.
    sources: Mapped[list["RecipeSource"]] = relationship(
        cascade="all, delete-orphan", order_by="RecipeSource.position"
    )


class RecipeSource(Base):
    __tablename__ = "recipe_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    position: Mapped[int]  # keeps the sources in order
    kind: Mapped[str]  # instagram, website, screenshot, text or manual
    url: Mapped[str | None]
    creators: Mapped[list[str]] = mapped_column(JSON)
