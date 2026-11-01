"""One more top-level category, at your request: "ממרחים, מטבלים ורטבים".

- Added unless you already have a top-level category by that name. Only into a notebook that already has
  categories: a new database gets it from the starter categories (app/seed.py), after the categories that
  0012 added, so with the same id.
- For recipes whose main purpose is to be spread, dipped into, poured over or added to another dish
  (flavored butter, pesto, hummus, tahini, a yogurt dip, a sauce made separately). A dish served
  alongside a main course is a side ("תוספות"); a whole dish that has a sauce (pasta in sauce) is not a
  sauce. The description says so, since the model classifies by it.
- No recipe changes: nothing is moved into it; you classify your recipes yourself.
Downgrade removes it, but only while no recipe is in it, it has no subcategory, and the description is
still this one.

Revision ID: 0013
Previous: 0012
Created: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out here, not imported: a migration must not change when the app's code does.
NAME = "ממרחים, מטבלים ורטבים"
DESCRIPTION = (
    "מתכונים שעיקר מטרתם למרוח, לטבול, לתבל או להוסיף טעם למנה אחרת: חמאה בטעמים, פסטו, חומוס, טחינה, "
    "מטבל יוגורט, רוטב לסלט או רוטב שמכינים בנפרד. תוספת שהיא מנה בפני עצמה (אורז, תפוחי אדמה, ירקות "
    "צלויים) שייכת לתוספות, ומנה שלמה שיש בה רוטב (פסטה ברוטב) אינה רוטב: לפי המתכון כולו."
)

_ADD = sa.text(
    "INSERT INTO categories (name, description, parent_id) SELECT :name, :description, NULL "
    "WHERE EXISTS (SELECT 1 FROM categories) "
    "AND NOT EXISTS (SELECT 1 FROM categories WHERE name = :name AND parent_id IS NULL)"
)
_REMOVE = sa.text(
    "DELETE FROM categories WHERE name = :name AND parent_id IS NULL AND description = :description "
    "AND NOT EXISTS (SELECT 1 FROM recipes WHERE recipes.category_id = categories.id) "
    "AND NOT EXISTS (SELECT 1 FROM categories AS sub WHERE sub.parent_id = categories.id)"
)


def upgrade() -> None:
    op.get_bind().execute(_ADD, {"name": NAME, "description": DESCRIPTION})


def downgrade() -> None:
    op.get_bind().execute(_REMOVE, {"name": NAME, "description": DESCRIPTION})
