"""Imported originals and draft review: recipes.status, recipes.issues, recipe_imports.

- recipes.status: 'draft' (imported, not reviewed yet) or 'saved'. Existing recipes become 'saved'.
- recipes.issues: what the person should check in a draft (JSON list). Existing recipes: [].
- recipe_imports: the original text exactly as pasted, one row per imported recipe. Saving a
  recipe never changes it; deleting the recipe deletes it.

Columns are added with SQLite's ALTER TABLE ... ADD COLUMN, which keeps the existing table
and its rows in place (no copy). SQLite checks the new CHECK constraint against every
existing row; the default 'saved' passes.

Revision ID: 0002
Previous: 0001
Created: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE recipes ADD COLUMN status VARCHAR NOT NULL DEFAULT 'saved' "
        "CONSTRAINT status_is_draft_or_saved CHECK (status IN ('draft', 'saved'))"
    )
    op.execute("ALTER TABLE recipes ADD COLUMN issues JSON NOT NULL DEFAULT '[]'")
    op.create_table(
        "recipe_imports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recipe_id"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("recipe_imports")
    op.execute("ALTER TABLE recipes DROP COLUMN issues")
    op.execute("ALTER TABLE recipes DROP COLUMN status")
