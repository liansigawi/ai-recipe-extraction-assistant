"""Desserts by type, and "קינוח בריא" as a separate attribute, at your request.

- recipes.healthy: whether a dessert is in your healthy style: 1 yes, 0 no, NULL not decided. Only a
  dessert can have it (app/crud.py checks; categories.healthy_style says which category is the desserts).
- What you had decided is kept: a recipe in "קינוחים בריאים" becomes healthy 1, one in "קינוחים רגילים"
  healthy 0. Every other recipe, desserts without a subcategory included, stays NULL: nothing undecided
  becomes a decision.
- Those two subcategories are then empty and removed; the six dessert types take their place under
  "קינוחים": עוגות, עוגיות וחיתוכיות, טארטים ופאי, קינוחי כוסות ומוסים, גלידות וקינוחים קפואים, מאפים
  מתוקים. No recipe gets a type: you (or the model, for a new import) choose it. Each type is added unless
  "קינוחים" already has a subcategory by its name.
- Only in a notebook with a top-level "קינוחים"; a new database gets the same from app/seed.py.
Downgrade puts each healthy (1) or regular (0) dessert back in "קינוחים בריאים" or "קינוחים רגילים" (its
type is lost), removes the types that are left unused with their descriptions unchanged, and drops both
columns.

Revision ID: 0014
Previous: 0013
Created: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out here, not imported: a migration must not change when the app's code does.
DESSERTS = "קינוחים"
HEALTHY, REGULAR = "קינוחים בריאים", "קינוחים רגילים"
# As migration 0007 wrote them, for the downgrade.
STYLE_DESCRIPTIONS = {
    REGULAR: "רוב הקינוחים: עוגות, עוגיות, מאפים, טארטים, בראוניז וקינוחי חלב שבנויים על קמח רגיל, סוכר, חמאה, "
    "שמנת או שוקולד. גם כשיש בהם קצת דבש, אגוזים או שקדים (למשל טארט דבש מלוח).",
    HEALTHY: "הסגנון האישי שלי: קינוחים שבנויים בעיקר על תמרים, שיבולת שועל, אגוזים, קמח שקדים או חמאת אגוזים, "
    "לפעמים ממותקים בדבש או במייפל, למשל כדורי תמרים ושיבולת שועל. לפי המתכון כולו ולא לפי מרכיב "
    "אחד; לא הערכה תזונתית, ולא בהכרח טבעוני או ללא חלב.",
}
TYPES = [
    (
        "עוגות",
        "עוגות: עוגות בחושות, בחושה ושוקולד, עוגות גבינה, עוגות שכבות וטורטים, עוגות ביסקוויטים, מאפינס "
        "וקאפקייקס, גם עוגה ללא אפייה.",
    ),
    (
        "עוגיות וחיתוכיות",
        "עוגיות וביסקוויטים, בראוניז ובלונדיז, חיתוכיות ומלבנים שחותכים מתבנית, וכדורים וחטיפים מתוקים "
        "(למשל כדורי תמרים).",
    ),
    (
        "טארטים ופאי",
        "טארטים, טארטלטים ופאי מתוקים: בסיס של בצק פריך או קראסט עם מילוי (קרם, פירות, שוקולד, גבינה).",
    ),
    (
        "קינוחי כוסות ומוסים",
        "קינוחים בכוס או בקערה: מוסים, פודינגים, קרמים, פנקוטה, טרייפל וקינוחי שכבות בכוס.",
    ),
    (
        "גלידות וקינוחים קפואים",
        "גלידות, סורבה, ארטיקים, פרוזן יוגורט וגלידת בננה, וקינוחים שמגישים קפואים.",
    ),
    (
        "מאפים מתוקים",
        "מאפים מתוקים מבצק או מבלילה: שמרים (באבקה, סינבון, רוגלך), סופגניות, בצק עלים, וגם פנקייקים, "
        "וופלים, קרפים ובלינצ'ס מתוקים; גם כששמם עוגה (עוגת שמרים).",
    ),
]

_DESSERTS_ID = "(SELECT id FROM categories WHERE name = :desserts AND parent_id IS NULL)"


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("ALTER TABLE categories ADD COLUMN healthy_style BOOLEAN NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE recipes ADD COLUMN healthy BOOLEAN")
    names = {"desserts": DESSERTS}
    bind.execute(sa.text(f"UPDATE categories SET healthy_style = 1 WHERE id = {_DESSERTS_ID}"), names)
    for name, value in ((HEALTHY, 1), (REGULAR, 0)):
        style = f"(SELECT id FROM categories WHERE name = :name AND parent_id = {_DESSERTS_ID})"
        bind.execute(sa.text(f"UPDATE recipes SET healthy = :value, subcategory_id = NULL WHERE subcategory_id = {style}"), {**names, "name": name, "value": value})
        bind.execute(sa.text(f"DELETE FROM categories WHERE id = {style}"), {**names, "name": name})
    for name, description in TYPES:
        bind.execute(
            sa.text(
                f"INSERT INTO categories (name, description, parent_id, healthy_style) SELECT :name, :description, {_DESSERTS_ID}, 0 "
                f"WHERE {_DESSERTS_ID} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM categories WHERE parent_id = {_DESSERTS_ID} AND name = :name)"
            ),
            {**names, "name": name, "description": description},
        )


def downgrade() -> None:
    bind = op.get_bind()
    names = {"desserts": DESSERTS}
    for name in (REGULAR, HEALTHY):
        bind.execute(
            sa.text(
                f"INSERT INTO categories (name, description, parent_id) SELECT :name, :description, {_DESSERTS_ID} "
                f"WHERE {_DESSERTS_ID} IS NOT NULL "
                f"AND NOT EXISTS (SELECT 1 FROM categories WHERE parent_id = {_DESSERTS_ID} AND name = :name)"
            ),
            {**names, "name": name, "description": STYLE_DESCRIPTIONS[name]},
        )
    for name, value in ((HEALTHY, 1), (REGULAR, 0)):
        style = f"(SELECT id FROM categories WHERE name = :name AND parent_id = {_DESSERTS_ID})"
        bind.execute(sa.text(f"UPDATE recipes SET subcategory_id = {style} WHERE category_id = {_DESSERTS_ID} AND healthy = :value"), {**names, "name": name, "value": value})
    types = f"(SELECT id FROM categories WHERE parent_id = {_DESSERTS_ID} AND name IN ({', '.join(f':t{i}' for i in range(len(TYPES)))}))"
    by_type = {f"t{i}": name for i, (name, _) in enumerate(TYPES)}
    bind.execute(sa.text(f"UPDATE recipes SET subcategory_id = NULL WHERE subcategory_id IN {types}"), {**names, **by_type})
    for name, description in TYPES:
        bind.execute(
            sa.text(
                f"DELETE FROM categories WHERE name = :name AND description = :description AND parent_id = {_DESSERTS_ID} "
                "AND NOT EXISTS (SELECT 1 FROM recipes WHERE recipes.subcategory_id = categories.id)"
            ),
            {**names, "name": name, "description": description},
        )
    op.execute("ALTER TABLE recipes DROP COLUMN healthy")
    op.execute("ALTER TABLE categories DROP COLUMN healthy_style")
