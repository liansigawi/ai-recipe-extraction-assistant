"""Clearer descriptions for the three starter categories.

The model chooses among the categories by their descriptions, and the old ones left the line
between "בישולים" and "ארוחות קלילות" unclear, did not say that a sweet dish with a little salt
or cheese is still a dessert, and did not say that a drink is not one. Only a description that
is still the starter text is replaced: one you have changed (or a category you renamed or added)
is left exactly as it is. No category is added, removed or renamed, and no recipe changes.

Revision ID: 0003
Previous: 0002
Created: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, starter description until now, the clearer description). Written out here, not imported:
# a migration must keep doing the same thing whatever app/sample_data.py says later.
DESCRIPTIONS = [
    (
        "קינוחים",
        "עוגות, עוגיות, מאפים מתוקים וקינוחים",
        "מאכלים מתוקים שאוכלים (לא משקאות), כקינוח או עם קפה: עוגות, עוגיות, מאפים מתוקים, "
        "פאי וטארטים מתוקים וקינוחים קרים. מתוק גם כשיש בו קצת מלח או גבינה.",
    ),
    (
        "בישולים",
        "מנות עיקריות ותבשילים",
        "מנות עיקריות מלוחות ומשביעות לארוחת צהריים או ערב מלאה: תבשילים וצלי, בשר, עוף ודגים "
        "כמנה עיקרית, מרקים, ומנות אורז, פסטה או קטניות.",
    ),
    (
        "ארוחות קלילות",
        "ארוחות קלות ומהירות, למשל פיצה מבצק יוגורט; לא בהכרח דל קלוריות",
        "ארוחות מלוחות קטנות או מהירות: סלטים, כריכים, מנות ביצים, מאפים מלוחים קטנים ומנות קטנות "
        "מטוגנות או אפויות, למשל פיצה מבצק יוגורט. בניגוד לבישולים, לא מנה עיקרית מלאה. לא בהכרח דל קלוריות.",
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
