"""The starter categories described by what you mean by them.

"קינוחים" is for sweet desserts, dairy desserts included; "ארוחות קלילות" for generally savory
dairy-based meals ("light" is a personal label, not about calories or portions); "בישולים" for
generally meat- or poultry-based main dishes. A dish without a clear fit (egg, vegetable, fish...)
stays unclassified. As in 0003, only a description that is still the text 0003 wrote is replaced:
one you have changed is left exactly as it is. No category is added, removed or renamed, and no
recipe changes.

Revision ID: 0004
Previous: 0003
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, the description 0003 wrote, the description by your meaning). Written out here, not imported.
DESCRIPTIONS = [
    (
        "קינוחים",
        "מאכלים מתוקים שאוכלים (לא משקאות), כקינוח או עם קפה: עוגות, עוגיות, מאפים מתוקים, "
        "פאי וטארטים מתוקים וקינוחים קרים. מתוק גם כשיש בו קצת מלח או גבינה.",
        "קינוחים מתוקים, כולל קינוחי חלב: עוגות, עוגיות, מאפים מתוקים, פאי וטארטים מתוקים וקינוחים קרים. "
        "מתוק גם כשיש בו קצת מלח או גבינה. לא משקאות.",
    ),
    (
        "בישולים",
        "מנות עיקריות מלוחות ומשביעות לארוחת צהריים או ערב מלאה: תבשילים וצלי, בשר, עוף ודגים "
        "כמנה עיקרית, מרקים, ומנות אורז, פסטה או קטניות.",
        "בדרך כלל מנות עיקריות על בסיס בשר או עוף.",
    ),
    (
        "ארוחות קלילות",
        "ארוחות מלוחות קטנות או מהירות: סלטים, כריכים, מנות ביצים, מאפים מלוחים קטנים ומנות קטנות "
        "מטוגנות או אפויות, למשל פיצה מבצק יוגורט. בניגוד לבישולים, לא מנה עיקרית מלאה. לא בהכרח דל קלוריות.",
        "בדרך כלל ארוחות מלוחות על בסיס חלבי (גבינות, יוגורט, שמנת), למשל טורטיות במילוי גבינה או פיצה "
        "מבצק יוגורט. \"קלילות\" הוא שם אישי, לא עניין של קלוריות או גודל מנה.",
    ),
]

_UPDATE = sa.text(
    "UPDATE categories SET description = :new WHERE name = :name AND parent_id IS NULL AND description = :old"
)


def upgrade() -> None:
    for name, old, new in DESCRIPTIONS:
        op.get_bind().execute(_UPDATE, {"name": name, "old": old, "new": new})


def downgrade() -> None:
    for name, old, new in DESCRIPTIONS:
        op.get_bind().execute(_UPDATE, {"name": name, "old": new, "new": old})
