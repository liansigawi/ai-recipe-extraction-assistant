"""Sample recipes for milestone 2, served by the read-only recipe endpoints.

Invented for this project (not copied from any source), and chosen to show the
cases the contract must handle: ingredient groups, an ingredient repeated in two
groups, softened vs melted butter, ingredients without a quantity, alternative
methods kept apart, reused cooking liquid, an English recipe and an unclassified one.

frontend/src/sampleRecipes.ts holds the same recipes for the user interface.
Keep the two in sync until milestone 3, when the database replaces both.
"""

from datetime import UTC, datetime

from app.schemas import CategoryRef, Ingredient, IngredientGroup, Recipe, Source, StepGroup

# The three starter categories from the brief. Milestone 3 stores them in the database.
DESSERTS = CategoryRef(id=1, name="קינוחים")
COOKING = CategoryRef(id=2, name="בישולים")
LIGHT_MEALS = CategoryRef(id=3, name="ארוחות קלילות")

CREATED = datetime(2026, 10, 19, 8, 0, tzinfo=UTC)


def ingredient(text: str, quantity: str | None) -> Ingredient:
    return Ingredient(text=text, quantity=quantity)


SAMPLE_RECIPES: list[Recipe] = [
    Recipe(
        id=1,
        title="עוגת שוקולד עם גנאש",
        category=DESSERTS,
        servings="12 פרוסות",
        ingredient_groups=[
            IngredientGroup(
                name="לעוגה",
                ingredients=[
                    ingredient("200 גרם שוקולד מריר", "200 גרם"),
                    ingredient("150 גרם חמאה מומסת", "150 גרם"),
                    ingredient("4 ביצים L", "4"),
                    ingredient("כוס סוכר", "כוס"),
                    ingredient("חצי כוס קמח", "חצי כוס"),
                    ingredient("קורט מלח", "קורט"),
                ],
            ),
            IngredientGroup(
                name="לגנאש",
                ingredients=[
                    ingredient("100 גרם שוקולד מריר", "100 גרם"),
                    ingredient("100 מ״ל שמנת מתוקה", "100 מ״ל"),
                    ingredient("30 גרם חמאה רכה", "30 גרם"),
                ],
            ),
        ],
        step_groups=[
            StepGroup(
                name="העוגה",
                steps=[
                    "מחממים תנור ל-170 מעלות ומשמנים תבנית בקוטר 24.",
                    "ממיסים את השוקולד עם החמאה ומצננים מעט.",
                    "טורפים את הביצים עם הסוכר והמלח, מוסיפים את תערובת השוקולד ואחריה את הקמח.",
                    "אופים 30–35 דקות, עד שקיסם יוצא עם פירורים לחים.",
                ],
            ),
            StepGroup(
                name="הגנאש",
                steps=[
                    "מחממים את השמנת עד סף רתיחה ושופכים על השוקולד.",
                    "ממתינים דקה, מערבבים עד שהתערובת חלקה ומוסיפים את החמאה הרכה.",
                    "מורחים על העוגה המצוננת.",
                ],
            ),
        ],
        notes=["אפשר להחליף את השמנת המתוקה בחלב קוקוס."],
        sources=[Source(kind="text")],
        created_at=CREATED,
        updated_at=CREATED,
    ),
    Recipe(
        id=2,
        title="עוף בסיר עם אורז",
        category=COOKING,
        servings="4 מנות",
        ingredient_groups=[
            IngredientGroup(
                ingredients=[
                    ingredient("עוף מחולק ל-8 חלקים", None),
                    ingredient("2 בצלים קצוצים", "2"),
                    ingredient("כפית כורכום", "כפית"),
                    ingredient("מלח ופלפל", None),
                    ingredient("4 כוסות מים", "4 כוסות"),
                    ingredient("2 כוסות אורז בסמטי", "2 כוסות"),
                ],
            ),
        ],
        step_groups=[
            StepGroup(
                name="הכנה",
                steps=[
                    "מטגנים את הבצל עד שהוא שקוף ומוסיפים את חלקי העוף.",
                    "מתבלים במלח, פלפל וכורכום ומוסיפים את המים.",
                ],
            ),
            StepGroup(name="בסיר לחץ", steps=["מבשלים 25 דקות מהרגע שהסיר מגיע ללחץ."]),
            StepGroup(name="בסיר רגיל", steps=["מבשלים על אש נמוכה כשעה וחצי, עד שהעוף רך."]),
            StepGroup(
                name="האורז",
                steps=[
                    "מסננים ושומרים את נוזלי הבישול.",
                    "מבשלים את האורז ב-3 כוסות מנוזלי הבישול של העוף (אם חסר, משלימים במים).",
                ],
            ),
        ],
        sources=[Source(kind="text")],
        created_at=CREATED,
        updated_at=CREATED,
    ),
    Recipe(
        id=3,
        title="פיצה מבצק יוגורט",
        category=LIGHT_MEALS,
        servings="2 פיצות אישיות",
        ingredient_groups=[
            IngredientGroup(
                name="לבצק",
                ingredients=[
                    ingredient("כוס יוגורט יווני", "כוס"),
                    ingredient("כוס וחצי קמח תופח", "כוס וחצי"),
                    ingredient("חצי כפית מלח", "חצי כפית"),
                ],
            ),
            IngredientGroup(
                name="לתוספות",
                ingredients=[
                    ingredient("חצי כוס רוטב עגבניות", "חצי כוס"),
                    ingredient("כוס מוצרלה מגורדת", "כוס"),
                    ingredient("זעתר", None),
                    ingredient("שמן זית", None),
                ],
            ),
        ],
        step_groups=[
            StepGroup(
                steps=[
                    "מערבבים את היוגורט, הקמח והמלח לבצק אחיד.",
                    "מחלקים לשני כדורים ומרדדים לעיגולים דקים.",
                    "מורחים רוטב, מפזרים מוצרלה וזעתר ומזלפים שמן זית.",
                    "אופים 12–15 דקות בתנור שחומם ל-220 מעלות.",
                ],
            ),
        ],
        notes=["אפשר להכין את הבצק יום מראש ולשמור במקרר."],
        sources=[Source(kind="website", url="https://example.com/yogurt-pizza")],
        created_at=CREATED,
        updated_at=CREATED,
    ),
    Recipe(
        id=4,
        title="Oat and Date Granola Bars",
        # Ambiguous between desserts and light meals, so it stays unclassified.
        category=None,
        servings="12 bars",
        ingredient_groups=[
            IngredientGroup(
                ingredients=[
                    ingredient("2 cups rolled oats", "2 cups"),
                    ingredient("1 cup pitted dates", "1 cup"),
                    ingredient("1/3 cup tahini", "1/3 cup"),
                    ingredient("2 tbsp honey", "2 tbsp"),
                    ingredient("a pinch of sea salt", "a pinch"),
                    ingredient("chopped almonds, for the top", None),
                ],
            ),
        ],
        step_groups=[
            StepGroup(
                steps=[
                    "Blend the dates with the tahini and honey into a thick paste.",
                    "Mix in the oats and salt, then press into a lined 20 cm square pan.",
                    "Scatter the almonds on top and chill for at least 2 hours before cutting.",
                ],
            ),
        ],
        notes=["Keeps for a week in the fridge."],
        sources=[Source(kind="website", url="https://example.com/granola-bars", creators=["Example Kitchen"])],
        created_at=CREATED,
        updated_at=CREATED,
    ),
]
