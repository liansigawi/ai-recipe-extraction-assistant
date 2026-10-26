"""Instagram imports: the post's address and where its caption was read, beside the original text.

- recipe_imports.url: the post the original came from (its canonical address), for a caption read
  from Instagram and for one pasted after a failed read. NULL for plain pasted text.
- recipe_imports.retrieved_from: "post_page" or "embed_view", which public page supplied a caption
  read automatically. NULL when the person pasted the text.

Both are part of the imported original, which saving a recipe never changes; the editable source
(recipe_sources) carries the address too, but the person may change that one. Columns are added
with ALTER TABLE ... ADD COLUMN, which keeps the rows in place; existing originals get NULL.

Revision ID: 0006
Previous: 0005
Created: 2026-10-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recipe_imports ADD COLUMN url VARCHAR")
    op.execute("ALTER TABLE recipe_imports ADD COLUMN retrieved_from VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE recipe_imports DROP COLUMN retrieved_from")
    op.execute("ALTER TABLE recipe_imports DROP COLUMN url")
