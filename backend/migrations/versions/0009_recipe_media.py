"""Recipes' pictures and videos: media_files (each file once, by its content) and recipe_media.

- media_files: a file under <data folder>/media, by its sha256, with its type and size.
- recipe_media: one of a recipe's pictures or videos: from its Instagram post (with the post's
  address and the item's place in it) or uploaded; "saved", or "thumbnail_only" for a video that could
  not be saved (its poster is); at most one cover per recipe. Deleted with its recipe.
New tables only: no existing row changes. Downgrade drops them (the files under media/ stay on disk).

Revision ID: 0009
Previous: 0008
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_table(
        "recipe_media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("thumbnail_file_id", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("post_url", sa.String(), nullable=True),
        sa.Column("post_shortcode", sa.String(), nullable=True),
        sa.Column("post_index", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("is_cover", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["media_files.id"]),
        sa.ForeignKeyConstraint(["thumbnail_file_id"], ["media_files.id"]),
        sa.UniqueConstraint("recipe_id", "post_shortcode", "post_index"),
        sa.CheckConstraint("kind IN ('image', 'video')", name="media_kind"),
        sa.CheckConstraint("status IN ('saved', 'thumbnail_only')", name="media_status"),
        sa.CheckConstraint("origin IN ('instagram', 'upload')", name="media_origin"),
        sa.CheckConstraint("file_id IS NOT NULL OR thumbnail_file_id IS NOT NULL", name="media_has_a_file"),
    )
    op.create_index("one_cover_per_recipe", "recipe_media", ["recipe_id"], unique=True, sqlite_where=sa.text("is_cover = 1"))


def downgrade() -> None:
    op.drop_index("one_cover_per_recipe", table_name="recipe_media")
    op.drop_table("recipe_media")
    op.drop_table("media_files")
