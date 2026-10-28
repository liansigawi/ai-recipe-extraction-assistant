"""The database tables, as SQLAlchemy classes. Each class is a table; each attribute is a column.

    categories        id, name, description, parent_id (NULL = top level)
    recipes           id, title, category_id, subcategory_id, servings,
                      ingredient_groups (JSON), step_groups (JSON), notes (JSON),
                      is_sample, created_at, updated_at, status, issues (JSON)
    recipe_sources    id, recipe_id, position, kind, url, creators (JSON)
    recipe_imports    id, recipe_id, kind, original_text, model, imported_at

Relationships:
- a subcategory is a category row whose parent_id points at a top-level category;
- a recipe points at a category and, optionally, one of its subcategories;
- a recipe has an ordered list of sources (one-to-many); deleting the recipe deletes them;
- an imported recipe has one original (one-to-one), which saving never changes.

Ordered recipe content (ingredient groups, step groups, notes) lives in JSON columns:
a recipe is always loaded and saved as a whole, so its lists need no tables of their own.

The tables themselves are created and changed by migrations (backend/migrations/), not from
these classes. tests/test_migrations.py checks that the two agree.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Text, UniqueConstraint, text
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
        CheckConstraint("status IN ('draft', 'saved')", name="status_is_draft_or_saved"),
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
    status: Mapped[str] = mapped_column(default="saved", server_default="saved")  # 'draft' or 'saved'
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, server_default="[]")
    # Whether you have cooked it: yours to mark, separate from the category and the draft status.
    cooked: Mapped[bool] = mapped_column(default=False, server_default=text("0"))

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
    # The imported original, if the recipe was imported. Saved with the recipe and deleted with it;
    # crud.py never assigns it after creation, so editing cannot change it.
    original: Mapped["RecipeImport | None"] = relationship(cascade="all, delete-orphan")
    # Its pictures and videos (app/media.py), deleted with it; the files themselves only when unused.
    media: Mapped[list["RecipeMedia"]] = relationship(cascade="all, delete-orphan", order_by="RecipeMedia.id")


class RecipeSource(Base):
    __tablename__ = "recipe_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    position: Mapped[int]  # keeps the sources in order
    kind: Mapped[str]  # instagram, website, screenshot, text or manual
    url: Mapped[str | None]
    creators: Mapped[list[dict]] = mapped_column(JSON)  # [{"name": ..., "username": ...}] (migration 0008)


class RecipeImport(Base):
    """The text a recipe was imported from, exactly as pasted or read. Kept apart from the editable recipe."""

    __tablename__ = "recipe_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), unique=True)
    kind: Mapped[str]  # "text" (pasted) or "instagram" (the caption, read from the post)
    original_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None]  # the model that read it; None: saved without a model
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime)
    url: Mapped[str | None]  # the post it came from, also for a caption pasted after a failed read
    retrieved_from: Mapped[str | None]  # "post_page" or "embed_view" for a caption read automatically
    # Who posted it, as read from the post: {"author": {"name", "username"}, "coauthors": [...]}.
    source_details: Mapped[dict | None] = mapped_column(JSON)


class MediaFile(Base):
    """A picture or video file under <data folder>/media, stored once by its content (sha256)."""

    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(unique=True)
    path: Mapped[str]  # relative to the media folder: "ab/ab12....jpg"
    content_type: Mapped[str]  # from the file's first bytes: image/jpeg, image/png, image/webp, image/gif, video/mp4
    size_bytes: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)


class RecipeMedia(Base):
    """One of a recipe's pictures or videos: from its Instagram post (in the post's order) or uploaded."""

    __tablename__ = "recipe_media"
    __table_args__ = (
        # A post's item once per recipe: fetching the post's media again adds nothing twice.
        UniqueConstraint("recipe_id", "post_shortcode", "post_index"),
        CheckConstraint("kind IN ('image', 'video')", name="media_kind"),
        CheckConstraint("status IN ('saved', 'thumbnail_only')", name="media_status"),
        CheckConstraint("origin IN ('instagram', 'upload')", name="media_origin"),
        CheckConstraint("file_id IS NOT NULL OR thumbnail_file_id IS NOT NULL", name="media_has_a_file"),
        # At most one cover per recipe.
        Index("one_cover_per_recipe", "recipe_id", unique=True, sqlite_where=text("is_cover = 1")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    kind: Mapped[str]  # "image" or "video"
    # "saved": the picture or video is here. "thumbnail_only": a video that could not be saved: its
    # poster is here, and the post's link plays it.
    status: Mapped[str]
    file_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id"))  # the picture or the video
    thumbnail_file_id: Mapped[int | None] = mapped_column(ForeignKey("media_files.id"))  # a video's poster
    origin: Mapped[str]  # "instagram" or "upload"
    post_url: Mapped[str | None]
    post_shortcode: Mapped[str | None]
    post_index: Mapped[int | None]  # its place in the post, from 0
    width: Mapped[int | None]
    height: Mapped[int | None]
    is_cover: Mapped[bool] = mapped_column(default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)

    file: Mapped[MediaFile | None] = relationship(foreign_keys=[file_id])
    thumbnail: Mapped[MediaFile | None] = relationship(foreign_keys=[thumbnail_file_id])
