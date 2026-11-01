"""Three top-level categories, at your request: "סלטים", "מרקים" and "תוספות".

- Each is added unless you already have a top-level category by that name. Only into a notebook that
  already has categories: a new database gets them from the starter categories (app/seed.py), after the
  dessert subcategories, so with the same ids.
- What the dish is decides over its main ingredient: a salad with cheese or chicken is a salad, a chicken
  or meat soup is a soup. "תוספות" is for what is served alongside a main course; a rice or legume dish
  that is the meal itself is not a side. The descriptions say so, since the model classifies by them.
- No recipe changes: nothing is moved into these categories; you classify your recipes yourself.
Downgrade removes them, but only while no recipe is in them, none has a subcategory, and the description
is still this one.

Revision ID: 0012
Previous: 0011
Created: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, description). Written out here, not imported: a migration must not change when the app's code does.
CATEGORIES = [
    (
        "סלטים",
        "סלטים: סלטי ירקות ועלים, וסלטים עשירים שמוגשים כארוחה (למשל סלט יווני, סלט קיסר, סלט טונה או סלט "
        "עם עוף). סלט שיש בו גבינה, עוף, בשר, טונה או ביצה שייך לכאן ולא לארוחות הבשריות או הקלילות: היותו "
        "סלט קובע, לא המרכיב העיקרי.",
    ),
    (
        "מרקים",
        "מרקים מכל סוג: מרקי ירקות, מרקי קטניות (עדשים, אפונה, שעועית), מרק עוף ומרקי בשר, גם מרק סמיך, "
        "קרם או מרק קר. מרק שייך לכאן גם כשיש בו עוף, בשר או גבינה: היותו מרק קובע, לא המרכיב העיקרי.",
    ),
    (
        "תוספות",
        "מנות שמוגשות בעיקר לצד מנה עיקרית: אורז, תפוחי אדמה, ירקות צלויים או מוקפצים, ותוספות של דגנים או "
        "קטניות (למשל בורגול, קוסקוס, פתיתים או שעועית ירוקה). לפי תפקיד המנה במתכון ולא לפי המרכיב: מנת "
        "אורז או קטניות שהיא הארוחה עצמה (למשל עוף ואורז בסיר אחד, או תבשיל עדשים כמנה עיקרית) לא כאן, "
        "וסלט שייך לסלטים.",
    ),
]

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
    for name, description in CATEGORIES:
        op.get_bind().execute(_ADD, {"name": name, "description": description})


def downgrade() -> None:
    for name, description in reversed(CATEGORIES):
        op.get_bind().execute(_REMOVE, {"name": name, "description": description})
