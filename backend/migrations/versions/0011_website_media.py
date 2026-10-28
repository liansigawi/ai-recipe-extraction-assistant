"""A recipe page's main picture: recipe_media.origin may be "website" too.

SQLite cannot change a CHECK constraint in place, so the table is rebuilt: a new one with the wider
rule, every row copied, the old one dropped, the new one renamed, its cover index made again. No row
changes. Downgrade deletes the website pictures' attachments (their files go when no recipe uses them)
and puts the narrower rule back.

Revision ID: 0011
Previous: 0010
Created: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    "id, recipe_id, kind, status, file_id, thumbnail_file_id, origin, post_url, post_shortcode, post_index, "
    "width, height, is_cover, created_at"
)


def _rebuild(origins: str) -> None:
    op.drop_index("one_cover_per_recipe", table_name="recipe_media")
    op.create_table(
        "recipe_media_rebuilt",
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
        sa.CheckConstraint(f"origin IN {origins}", name="media_origin"),
        sa.CheckConstraint("file_id IS NOT NULL OR thumbnail_file_id IS NOT NULL", name="media_has_a_file"),
    )
    op.execute(f"INSERT INTO recipe_media_rebuilt ({COLUMNS}) SELECT {COLUMNS} FROM recipe_media")
    op.drop_table("recipe_media")
    op.rename_table("recipe_media_rebuilt", "recipe_media")
    op.create_index("one_cover_per_recipe", "recipe_media", ["recipe_id"], unique=True, sqlite_where=sa.text("is_cover = 1"))


def upgrade() -> None:
    _rebuild("('instagram', 'upload', 'website')")


def downgrade() -> None:
    op.execute("DELETE FROM recipe_media WHERE origin = 'website'")
    _rebuild("('instagram', 'upload')")
