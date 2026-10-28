// Test data: the four invented sample recipes and the starter categories, shaped as the API
// returns them. The page itself loads recipes from the API; the real samples are seeded into
// the database by backend/app/sample_data.py.
import type { Category, CategoryRef, Ingredient, Recipe } from '../types'

export const sampleCategories: Category[] = [
  { id: 1, name: 'קינוחים', description: 'עוגות, עוגיות, מאפים מתוקים וקינוחים', subcategories: [] },
  { id: 2, name: 'בישולים', description: 'מנות עיקריות ותבשילים', subcategories: [] },
  { id: 3, name: 'ארוחות קלילות', description: 'ארוחות קלות ומהירות, למשל פיצה מבצק יוגורט; לא בהכרח דל קלוריות', subcategories: [] },
]

const desserts: CategoryRef = { id: 1, name: 'קינוחים' }
const cooking: CategoryRef = { id: 2, name: 'בישולים' }
const lightMeals: CategoryRef = { id: 3, name: 'ארוחות קלילות' }

const created = '2026-10-19T08:00:00Z'

function ingredient(text: string, quantity: string | null): Ingredient {
  return { text, quantity }
}

export const sampleRecipes: Recipe[] = [
  {
    id: 1,
    title: 'עוגת שוקולד עם גנאש',
    category: desserts,
    subcategory: null,
    servings: '12 פרוסות',
    ingredient_groups: [
      {
        name: 'לעוגה',
        ingredients: [
          ingredient('200 גרם שוקולד מריר', '200 גרם'),
          ingredient('150 גרם חמאה מומסת', '150 גרם'),
          ingredient('4 ביצים L', '4'),
          ingredient('כוס סוכר', 'כוס'),
          ingredient('חצי כוס קמח', 'חצי כוס'),
          ingredient('קורט מלח', 'קורט'),
        ],
      },
      {
        name: 'לגנאש',
        ingredients: [
          ingredient('100 גרם שוקולד מריר', '100 גרם'),
          ingredient('100 מ״ל שמנת מתוקה', '100 מ״ל'),
          ingredient('30 גרם חמאה רכה', '30 גרם'),
        ],
      },
    ],
    step_groups: [
      {
        name: 'העוגה',
        steps: [
          'מחממים תנור ל-170 מעלות ומשמנים תבנית בקוטר 24.',
          'ממיסים את השוקולד עם החמאה ומצננים מעט.',
          'טורפים את הביצים עם הסוכר והמלח, מוסיפים את תערובת השוקולד ואחריה את הקמח.',
          'אופים 30–35 דקות, עד שקיסם יוצא עם פירורים לחים.',
        ],
      },
      {
        name: 'הגנאש',
        steps: [
          'מחממים את השמנת עד סף רתיחה ושופכים על השוקולד.',
          'ממתינים דקה, מערבבים עד שהתערובת חלקה ומוסיפים את החמאה הרכה.',
          'מורחים על העוגה המצוננת.',
        ],
      },
    ],
    notes: ['אפשר להחליף את השמנת המתוקה בחלב קוקוס.'],
    sources: [{ kind: 'text', url: null, creators: [] }],
    created_at: created,
    updated_at: created,
    is_sample: true,
    status: 'saved',
    issues: [],
    cooked: false,
    original: null,
    media: [],
    cover_id: null,
  },
  {
    id: 2,
    title: 'עוף בסיר עם אורז',
    category: cooking,
    subcategory: null,
    servings: '4 מנות',
    ingredient_groups: [
      {
        name: null,
        ingredients: [
          ingredient('עוף מחולק ל-8 חלקים', null),
          ingredient('2 בצלים קצוצים', '2'),
          ingredient('כפית כורכום', 'כפית'),
          ingredient('מלח ופלפל', null),
          ingredient('4 כוסות מים', '4 כוסות'),
          ingredient('2 כוסות אורז בסמטי', '2 כוסות'),
        ],
      },
    ],
    step_groups: [
      {
        name: 'הכנה',
        steps: [
          'מטגנים את הבצל עד שהוא שקוף ומוסיפים את חלקי העוף.',
          'מתבלים במלח, פלפל וכורכום ומוסיפים את המים.',
        ],
      },
      { name: 'בסיר לחץ', steps: ['מבשלים 25 דקות מהרגע שהסיר מגיע ללחץ.'] },
      { name: 'בסיר רגיל', steps: ['מבשלים על אש נמוכה כשעה וחצי, עד שהעוף רך.'] },
      {
        name: 'האורז',
        steps: [
          'מסננים ושומרים את נוזלי הבישול.',
          'מבשלים את האורז ב-3 כוסות מנוזלי הבישול של העוף (אם חסר, משלימים במים).',
        ],
      },
    ],
    notes: [],
    sources: [{ kind: 'text', url: null, creators: [] }],
    created_at: created,
    updated_at: created,
    is_sample: true,
    status: 'saved',
    issues: [],
    cooked: false,
    original: null,
    media: [],
    cover_id: null,
  },
  {
    id: 3,
    title: 'פיצה מבצק יוגורט',
    category: lightMeals,
    subcategory: null,
    servings: '2 פיצות אישיות',
    ingredient_groups: [
      {
        name: 'לבצק',
        ingredients: [
          ingredient('כוס יוגורט יווני', 'כוס'),
          ingredient('כוס וחצי קמח תופח', 'כוס וחצי'),
          ingredient('חצי כפית מלח', 'חצי כפית'),
        ],
      },
      {
        name: 'לתוספות',
        ingredients: [
          ingredient('חצי כוס רוטב עגבניות', 'חצי כוס'),
          ingredient('כוס מוצרלה מגורדת', 'כוס'),
          ingredient('זעתר', null),
          ingredient('שמן זית', null),
        ],
      },
    ],
    step_groups: [
      {
        name: null,
        steps: [
          'מערבבים את היוגורט, הקמח והמלח לבצק אחיד.',
          'מחלקים לשני כדורים ומרדדים לעיגולים דקים.',
          'מורחים רוטב, מפזרים מוצרלה וזעתר ומזלפים שמן זית.',
          'אופים 12–15 דקות בתנור שחומם ל-220 מעלות.',
        ],
      },
    ],
    notes: ['אפשר להכין את הבצק יום מראש ולשמור במקרר.'],
    sources: [{ kind: 'website', url: 'https://example.com/yogurt-pizza', creators: [] }],
    created_at: created,
    updated_at: created,
    is_sample: true,
    status: 'saved',
    issues: [],
    cooked: false,
    original: null,
    media: [],
    cover_id: null,
  },
  {
    id: 4,
    title: 'Oat and Date Granola Bars',
    // Ambiguous between desserts and light meals, so it stays unclassified.
    category: null,
    subcategory: null,
    servings: '12 bars',
    ingredient_groups: [
      {
        name: null,
        ingredients: [
          ingredient('2 cups rolled oats', '2 cups'),
          ingredient('1 cup pitted dates', '1 cup'),
          ingredient('1/3 cup tahini', '1/3 cup'),
          ingredient('2 tbsp honey', '2 tbsp'),
          ingredient('a pinch of sea salt', 'a pinch'),
          ingredient('chopped almonds, for the top', null),
        ],
      },
    ],
    step_groups: [
      {
        name: null,
        steps: [
          'Blend the dates with the tahini and honey into a thick paste.',
          'Mix in the oats and salt, then press into a lined 20 cm square pan.',
          'Scatter the almonds on top and chill for at least 2 hours before cutting.',
        ],
      },
    ],
    notes: ['Keeps for a week in the fridge.'],
    sources: [{ kind: 'website', url: 'https://example.com/granola-bars', creators: [{ name: 'Example Kitchen', username: null }] }],
    created_at: created,
    updated_at: created,
    is_sample: true,
    status: 'saved',
    issues: [],
    cooked: false,
    original: null,
    media: [],
    cover_id: null,
  },
]
