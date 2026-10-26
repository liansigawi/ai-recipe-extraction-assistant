"""Credit as a name and an Instagram username; who posted an imported post, kept with its original.

- recipe_sources.creators: each credit was one string; now {"name": ..., "username": ...}. "@user", and
  on an Instagram source a bare username (as imports stored them), becomes a username; anything else a
  name. The same rule reads old strings in the API (schemas.creator_from_text).
- recipe_imports.source_details (JSON, NULL for existing originals): the post's author and co-authors
  as read from Instagram, kept apart from the credit you edit.
No recipe's content changes. Downgrade turns each credit back into one string (the username for an
Instagram source, else the name) and drops the new column.

Revision ID: 0008
Previous: 0007
Created: 2026-10-26
"""

import json
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

USERNAME = re.compile(r"[A-Za-z0-9._]{1,30}")  # written out here: a migration must not change with the app


def _structured(text: str, kind: str) -> dict:
    text = text.strip()
    bare = text.removeprefix("@")
    if (text.startswith("@") or kind == "instagram") and USERNAME.fullmatch(bare):
        return {"name": None, "username": bare}
    return {"name": text, "username": None}


def _as_text(credit: dict, kind: str) -> str:
    if kind == "instagram" and credit.get("username"):
        return credit["username"]
    return credit.get("name") or f"@{credit.get('username')}"


def _rewrite(convert) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, kind, creators FROM recipe_sources")).fetchall()
    for row_id, kind, creators in rows:
        credits = json.loads(creators) if isinstance(creators, str) else creators
        bind.execute(
            sa.text("UPDATE recipe_sources SET creators = :creators WHERE id = :id"),
            {"id": row_id, "creators": json.dumps([convert(credit, kind) for credit in credits or []], ensure_ascii=False)},
        )


def upgrade() -> None:
    op.execute("ALTER TABLE recipe_imports ADD COLUMN source_details JSON")
    _rewrite(lambda credit, kind: _structured(credit, kind) if isinstance(credit, str) else credit)


def downgrade() -> None:
    _rewrite(lambda credit, kind: _as_text(credit, kind) if isinstance(credit, dict) else credit)
    op.execute("ALTER TABLE recipe_imports DROP COLUMN source_details")
