"""Two subcategories under "קינוחים", at your request: "קינוחים רגילים" and "קינוחים בריאים".

- Added under the top-level category named "קינוחים", each unless that category already has a
  subcategory by that name. Only into a notebook that has that category: a new database gets them
  from the starter categories (app/seed.py), with the same ids.
- No recipe changes: existing desserts stay in "קינוחים" without a subcategory until you choose one.
Downgrade removes them, but only while no recipe is in them and their description is still this one.

Revision ID: 0007
Previous: 0006
Created: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PARENT = "קינוחים"
# (name, description). Written out here, not imported: a migration must not change when the app's code does.
SUBCATEGORIES = [
    (
        "קינוחים רגילים",
        "רוב הקינוחים: עוגות, עוגיות, מאפים, טארטים, בראוניז וקינוחי חלב שבנויים על קמח רגיל, סוכר, חמאה, "
        "שמנת או שוקולד. גם כשיש בהם קצת דבש, אגוזים או שקדים (למשל טארט דבש מלוח).",
    ),
    (
        "קינוחים בריאים",
        "הסגנון האישי שלי: קינוחים שבנויים בעיקר על תמרים, שיבולת שועל, אגוזים, קמח שקדים או חמאת אגוזים, "
        "לפעמים ממותקים בדבש או במייפל, למשל כדורי תמרים ושיבולת שועל. לפי המתכון כולו ולא לפי מרכיב "
        "אחד; לא הערכה תזונתית, ולא בהכרח טבעוני או ללא חלב.",
    ),
]

_ADD = sa.text(
    "INSERT INTO categories (name, description, parent_id) "
    "SELECT :name, :description, parent.id FROM categories AS parent "
    "WHERE parent.name = :parent AND parent.parent_id IS NULL "
    "AND NOT EXISTS (SELECT 1 FROM categories AS sub WHERE sub.parent_id = parent.id AND sub.name = :name)"
)
_REMOVE = sa.text(
    "DELETE FROM categories WHERE name = :name AND description = :description "
    "AND parent_id IN (SELECT id FROM categories WHERE name = :parent AND parent_id IS NULL) "
    "AND NOT EXISTS (SELECT 1 FROM recipes WHERE recipes.subcategory_id = categories.id)"
)


def upgrade() -> None:
    for name, description in SUBCATEGORIES:
        op.get_bind().execute(_ADD, {"name": name, "description": description, "parent": PARENT})


def downgrade() -> None:
    for name, description in SUBCATEGORIES:
        op.get_bind().execute(_REMOVE, {"name": name, "description": description, "parent": PARENT})
