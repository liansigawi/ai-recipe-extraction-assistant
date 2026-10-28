"""Whether you have cooked a recipe: recipes.cooked, 0 (not yet) for every recipe until you mark it.

Nothing is guessed from existing data: categories, drafts and everything else stay as they are.
Downgrade drops the column (and with it the marks).

Revision ID: 0010
Previous: 0009
Created: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recipes ADD COLUMN cooked BOOLEAN NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE recipes DROP COLUMN cooked")
