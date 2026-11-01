"""Seed data for a new database: the starter categories and four sample recipes.

The sample recipes were INVENTED for this project. They are not copies or edited
versions of any real recipe or of the Instagram posts used in milestone 1. They exist
to show the cases the contract must handle: ingredient groups, an ingredient repeated
in two groups, softened vs melted butter, ingredients without a quantity, alternative
methods kept apart, reused cooking liquid, an English recipe and an unclassified one.

They are written once, into a brand-new database, with is_sample=True, so the page
labels them as examples. You can edit or delete them like any other recipe.
"""

from app.schemas import Ingredient, IngredientGroup, RecipeInput, Source, StepGroup

# The starter categories: (name, description). The brief's three, with "בישולים" renamed "ארוחות בשריות",
# and "משקאות", which you added. After this, only you manage categories.
# The model chooses a category by these descriptions, which say what you mean by each: sweet desserts;
# meat and poultry meals; savory dairy or egg meals ("light" is your own label, not about calories or
# portions); drinks. A dish without a clear fit stays unclassified. Migrations 0003 to 0005 brought older
# databases up to these.
STARTER_CATEGORIES: list[tuple[str, str]] = [
    (
        "קינוחים",
        "קינוחים מתוקים, כולל קינוחי חלב: עוגות, עוגיות, מאפינס, מאפים מתוקים, פאי וטארטים מתוקים וקינוחים "
        "קרים. מתוק גם כשיש בו מלח (קרמל מלוח, דבש מלוח) או גבינה. לא משקאות.",
    ),
    (
        "ארוחות בשריות",
        "ארוחות שיש בהן בשר בקר, טלה, הודו או עוף כמרכיב עיקרי: תבשילים, צלי, קציצות, שניצל, פרגיות, כרעיים "
        "ומנות עוף אחרות. מנה בלי בשר ובלי עוף (למשל דגים, פסטה עם גבינה, קטניות) לא כאן.",
    ),
    (
        "ארוחות קלילות",
        "ארוחות לא מתוקות על בסיס חלבי או ביצים, בלי בשר: פסטה במילוי גבינה (כמו קונכיות או רביולי ממולאים), "
        "פיצה מבצק יוגורט, טורטיות במילוי גבינה, פשטידות, חביתות ושקשוקה. \"קלילות\" הוא שם אישי, לא עניין של "
        "קלוריות או גודל מנה.",
    ),
    (
        "משקאות",
        "משקאות: שייקים וסמוטי, משקאות קפה, לימונדה (גם גרוסה או קפואה) ומשקאות קרים או חמים אחרים. "
        "משקה מתוק או על בסיס חלב שייך לכאן, לא לקינוחים.",
    ),
]

# The starter subcategories, by their category's name: (name, description). "קינוחים בריאים" is your own
# style of dessert, judged by the whole recipe, not a nutritional verdict and not "vegan" or "dairy-free".
# A dessert whose style is unclear stays in "קינוחים" without a subcategory. Migration 0007 added these
# to older databases.
STARTER_SUBCATEGORIES: dict[str, list[tuple[str, str]]] = {
    "קינוחים": [
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
    ],
}

# Three more top-level categories you asked for (2026-11-01), created after the subcategories so a new
# database gives them the same ids as an older one that migration 0012 upgraded. What the dish is decides
# over its main ingredient: a cheese or chicken salad is a salad, a chicken or meat soup is a soup. A side
# is judged by its role: a rice or legume dish that is the meal itself is not one.
ADDED_CATEGORIES: list[tuple[str, str]] = [
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


def ingredient(text: str, quantity: str | None) -> Ingredient:
    return Ingredient(text=text, quantity=quantity)


# (category name or None, recipe). The category id is looked up when seeding.
SAMPLE_RECIPES: list[tuple[str | None, RecipeInput]] = [
    (
        "קינוחים",
        RecipeInput(
            title="עוגת שוקולד עם גנאש",
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
        ),
    ),
    (
        "ארוחות בשריות",
        RecipeInput(
            title="עוף בסיר עם אורז",
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
        ),
    ),
    (
        "ארוחות קלילות",
        RecipeInput(
            title="פיצה מבצק יוגורט",
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
        ),
    ),
    (
        None,  # ambiguous between desserts and light meals, so it stays unclassified
        RecipeInput(
            title="Oat and Date Granola Bars",
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
        ),
    ),
]
