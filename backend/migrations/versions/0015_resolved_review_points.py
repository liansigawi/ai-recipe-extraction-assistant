"""The review points you resolved, kept with the recipe: recipes.resolved_issues, a JSON list, empty for
every recipe until you resolve a point in review.

Each entry is the point as the import raised it, with what you did about it: "added" (you approved adding
the ingredient it proposes), "dismissed" (you chose to ignore it) or "handled" (you marked it done). A
dismissal belongs to that point of that recipe only. Nothing is guessed from existing data: open points
(recipes.issues) and everything else stay as they are. Downgrade drops the column (and with it the record).

Revision ID: 0015
Previous: 0014
Created: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recipes ADD COLUMN resolved_issues JSON NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE recipes DROP COLUMN resolved_issues")
