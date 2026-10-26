"""Your categories, reorganized: "בישולים" becomes "ארוחות בשריות", and "משקאות" is added.

- "בישולים" is renamed in place: same id, so every recipe in it stays in it. Not renamed if you
  have already renamed it, or if you already have a category called "ארוחות בשריות".
- "משקאות" is added at your request, unless you already have a category by that name. Only into a
  notebook that already has categories: a new database gets it from the starter categories.
- The descriptions take your new meaning: meat and poultry meals; savory dairy or egg meals;
  sweet desserts; drinks. As before, only a description that is still the text 0004 wrote is
  replaced: one you have changed is left exactly as it is.
No recipe changes. Downgrade reverses all three, but removes "משקאות" only while no recipe is in it.

Revision ID: 0005
Previous: 0004
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_NAME, NEW_NAME = "בישולים", "ארוחות בשריות"
DRINKS = "משקאות"
DRINKS_DESCRIPTION = (
    "משקאות: שייקים וסמוטי, משקאות קפה, לימונדה (גם גרוסה או קפואה) ומשקאות קרים או חמים אחרים. "
    "משקה מתוק או על בסיס חלב שייך לכאן, לא לקינוחים."
)

# (name after the rename, the description 0004 wrote, the description by your new meaning). Written out here, not imported.
DESCRIPTIONS = [
    (
        "קינוחים",
        "קינוחים מתוקים, כולל קינוחי חלב: עוגות, עוגיות, מאפים מתוקים, פאי וטארטים מתוקים וקינוחים קרים. "
        "מתוק גם כשיש בו קצת מלח או גבינה. לא משקאות.",
        "קינוחים מתוקים, כולל קינוחי חלב: עוגות, עוגיות, מאפינס, מאפים מתוקים, פאי וטארטים מתוקים וקינוחים "
        "קרים. מתוק גם כשיש בו מלח (קרמל מלוח, דבש מלוח) או גבינה. לא משקאות.",
    ),
    (
        NEW_NAME,
        "בדרך כלל מנות עיקריות על בסיס בשר או עוף.",
        "ארוחות שיש בהן בשר בקר, טלה, הודו או עוף כמרכיב עיקרי: תבשילים, צלי, קציצות, שניצל, פרגיות, כרעיים "
        "ומנות עוף אחרות. מנה בלי בשר ובלי עוף (למשל דגים, פסטה עם גבינה, קטניות) לא כאן.",
    ),
    (
        "ארוחות קלילות",
        "בדרך כלל ארוחות מלוחות על בסיס חלבי (גבינות, יוגורט, שמנת), למשל טורטיות במילוי גבינה או פיצה "
        "מבצק יוגורט. \"קלילות\" הוא שם אישי, לא עניין של קלוריות או גודל מנה.",
        "ארוחות לא מתוקות על בסיס חלבי או ביצים, בלי בשר: פסטה במילוי גבינה (כמו קונכיות או רביולי ממולאים), "
        "פיצה מבצק יוגורט, טורטיות במילוי גבינה, פשטידות, חביתות ושקשוקה. \"קלילות\" הוא שם אישי, לא עניין של "
        "קלוריות או גודל מנה.",
    ),
]

_RENAME = sa.text(
    "UPDATE categories SET name = :new WHERE name = :old AND parent_id IS NULL "
    "AND NOT EXISTS (SELECT 1 FROM categories WHERE name = :new AND parent_id IS NULL)"
)
_DESCRIBE = sa.text(
    "UPDATE categories SET description = :new WHERE name = :name AND parent_id IS NULL AND description = :old"
)
_ADD_DRINKS = sa.text(
    "INSERT INTO categories (name, description, parent_id) SELECT :name, :description, NULL "
    "WHERE EXISTS (SELECT 1 FROM categories) "
    "AND NOT EXISTS (SELECT 1 FROM categories WHERE name = :name AND parent_id IS NULL)"
)
_REMOVE_DRINKS = sa.text(
    "DELETE FROM categories WHERE name = :name AND parent_id IS NULL AND description = :description "
    "AND NOT EXISTS (SELECT 1 FROM recipes WHERE recipes.category_id = categories.id) "
    "AND NOT EXISTS (SELECT 1 FROM categories AS sub WHERE sub.parent_id = categories.id)"
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(_RENAME, {"old": OLD_NAME, "new": NEW_NAME})
    for name, old, new in DESCRIPTIONS:
        bind.execute(_DESCRIBE, {"name": name, "old": old, "new": new})
    bind.execute(_ADD_DRINKS, {"name": DRINKS, "description": DRINKS_DESCRIPTION})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(_REMOVE_DRINKS, {"name": DRINKS, "description": DRINKS_DESCRIPTION})
    for name, old, new in DESCRIPTIONS:
        bind.execute(_DESCRIBE, {"name": name, "old": new, "new": old})
    bind.execute(_RENAME, {"old": NEW_NAME, "new": OLD_NAME})
