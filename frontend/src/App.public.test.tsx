import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Demonstration, PublicNotebook, Recipe } from './types'

// The public, read-only copy: the same App, built with `vite build --mode public`. It reads one exported
// file (notebook.json) instead of the API, and offers nothing that changes data.

const DRINK = 'משקה טרנדי - שייק בננה תמר ואייס קפה'
const TORTE = 'טורט וניל עם קרם מסקרפונה ותותים'
const CAKE = 'עוגת קפה ושוקולד'

const DECORATE = 'לקשט בתותים ולהנות מביס מושלם!'
const BAKING = 'אופים על 150 מעלות (כל תנור עובד אחרת).'
const STRAWBERRIES = {
  kind: 'ingredient_only_in_steps' as const,
  message: 'המצרך "תותים" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
  quote: DECORATE,
  proposed: { text: 'תותים', quantity: null, group: null },
}
// The torte's caption imported again, as recorded: a wrong type in the draft, corrected in review; the strawberries added.
const demonstration: Demonstration = {
  run_at: '2026-11-04T17:10:00Z',
  model: 'qwen3:8b',
  draft: {
    title: TORTE,
    servings: null,
    category: { id: 1, name: 'קינוחים' },
    subcategory: { id: 13, name: 'טארטים ופאי' },
    healthy: null,
    ingredient_groups: [{ name: 'טורט וניל', ingredients: [{ text: '4 ביצים L', quantity: '4' }] }],
    step_groups: [{ name: null, steps: [BAKING, DECORATE] }],
    notes: [],
    issues: [STRAWBERRIES],
    saved_at: '2026-11-04T17:10:00Z',
  },
  reviewed: {
    title: TORTE,
    servings: null,
    category: { id: 1, name: 'קינוחים' },
    subcategory: { id: 11, name: 'עוגות' },
    healthy: false,
    ingredient_groups: [
      { name: 'טורט וניל', ingredients: [{ text: '4 ביצים L', quantity: '4' }] },
      { name: null, ingredients: [{ text: 'תותים', quantity: null, derived_from: DECORATE, added_in_review: true }] },
    ],
    step_groups: [{ name: null, steps: [BAKING, DECORATE] }],
    notes: [],
    resolved_issues: [{ ...STRAWBERRIES, resolution: 'added' }],
    issues: [],
    saved_at: '2026-11-04T17:20:00Z',
  },
}

const drinks = { id: 4, name: 'משקאות' }
const desserts = { id: 1, name: 'קינוחים' }

function recipe(fields: Partial<Recipe> & Pick<Recipe, 'id' | 'title'>): Recipe {
  return {
    category: desserts,
    subcategory: null,
    healthy: null,
    servings: null,
    ingredient_groups: [{ name: null, ingredients: [{ text: '3 ביצים L', quantity: '3' }] }],
    step_groups: [{ name: null, steps: ['מערבבים ואופים.'] }],
    notes: [],
    sources: [],
    is_sample: false,
    status: 'saved',
    issues: [],
    resolved_issues: [],
    cooked: false,
    original: null,
    media: [],
    cover_id: null,
    created_at: '2026-10-28T11:40:26Z',
    updated_at: '2026-10-28T11:44:09Z',
    processing: null,
    ...fields,
  }
}

const notebook: PublicNotebook = {
  exported_at: '2026-11-01T10:33:00Z',
  repository_url: 'https://github.com/example/recipes',
  categories: [
    // As exported before any dessert has a type: the desserts, with their healthy style, and no type in use.
    { id: 1, name: 'קינוחים', description: null, subcategories: [], healthy_style: true },
    { id: 4, name: 'משקאות', description: null, subcategories: [] },
  ],
  recipes: [
    recipe({ id: 15, title: CAKE, cooked: true, healthy: true }),
    recipe({
      id: 12,
      title: TORTE,
      cooked: true,
      sources: [{ kind: 'instagram', url: 'https://www.instagram.com/p/Cm1mCdCpSzJ/', creators: [{ name: 'ריטה קדוש', username: 'ritakadosh_' }] }],
      original: {
        kind: 'instagram',
        text: 'טורט וניל 🍓\n4 ביצים L\nמקציפים ואופים.',
        model: 'qwen3:8b',
        imported_at: '2026-10-28T11:40:26Z',
        url: 'https://www.instagram.com/p/Cm1mCdCpSzJ/',
        retrieved_from: 'post_page',
        author: { name: 'ריטה קדוש', username: 'ritakadosh_' },
        coauthors: [],
      },
      processing: { draft: null, demonstration },
    }),
    recipe({
      id: 6,
      title: DRINK,
      category: drinks,
      ingredient_groups: [{ name: null, ingredients: [{ text: 'חצי תמר מג׳הול', quantity: 'חצי' }] }],
      step_groups: [{ name: null, steps: ['לערבל הכל יחד.'] }],
      created_at: '2026-10-20T10:52:14Z',
      updated_at: '2026-10-26T14:21:42Z',
      original: {
        kind: 'text',
        text: 'הגירסה שלי:\nחצי תמר מג׳הול\n\nלערבל הכל יחד.',
        model: 'qwen3:8b',
        imported_at: '2026-10-20T10:52:14Z',
        url: null,
        retrieved_from: null,
        author: null,
        coauthors: [],
      },
      processing: {
        draft: {
          title: DRINK,
          servings: null,
          category: null,
          subcategory: null,
          ingredient_groups: [{ name: null, ingredients: [{ text: 'חצי תמר מג׳ hollow', quantity: 'חצי' }] }],
          step_groups: [{ name: null, steps: ['לערבל הכל יחד.'] }],
          notes: [],
          issues: [{ kind: 'not_found_in_source', message: 'השורה "חצי תמר מג׳ hollow" לא מופיעה כך בטקסט המקורי.', quote: null }],
          saved_at: '2026-10-20T10:52:14Z',
        },
      },
    }),
  ],
}

let requests: { url: string; method: string }[]

beforeEach(() => {
  vi.stubEnv('MODE', 'public')
  requests = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, method: init?.method ?? 'GET' })
      return new Response(JSON.stringify(notebook), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
})

async function renderCopy() {
  render(<App />)
  await screen.findByRole('region', { name: 'המתכונים' })
}

const gallery = () => within(screen.getByRole('region', { name: 'המתכונים' }))

async function openRecipe(user: ReturnType<typeof userEvent.setup>, title: string) {
  await user.click(gallery().getByRole('button', { name: new RegExp(title) }))
  return screen.getByRole('heading', { level: 2, name: title })
}

describe('the public copy', () => {
  it('shows the exported recipes, read from its one file, and nothing that changes them', async () => {
    await renderCopy()
    expect(gallery().getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByRole('region', { name: 'על העותק הזה' })).toHaveTextContent('ברוכים הבאים למחברת המתכונים שלי.')
    expect(screen.getByRole('button', { name: 'איך זה עובד' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ייבוא מתכון/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'קטגוריות' })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /קישור/ })).not.toBeInTheDocument()
    // The cooked marks are text, not buttons; the filters still count them. No drafts, so no drafts filter.
    expect(screen.queryByRole('button', { name: 'כבר הכנתי' })).not.toBeInTheDocument()
    expect(gallery().getAllByText('כבר הכנתי')).toHaveLength(2)
    expect(screen.getByRole('radio', { name: /כבר הכנתי 2/ })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'טיוטות' })).not.toBeInTheDocument()
    expect(requests).toEqual([{ url: '/notebook.json', method: 'GET' }])
  })

  it('offers the healthy-style filter for the desserts even before any dessert has a type', async () => {
    const user = userEvent.setup()
    await renderCopy()
    await user.click(within(screen.getByRole('group', { name: 'קטגוריה' })).getByRole('radio', { name: 'קינוחים' }))
    await user.click(screen.getByRole('checkbox', { name: 'קינוח בריא' }))
    expect(gallery().getAllByRole('listitem')).toHaveLength(1)
    expect(gallery().getByText(CAKE)).toBeInTheDocument()
  })

  it('a recipe has no edit or delete, and shows its cooked mark as saved', async () => {
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, CAKE)
    expect(screen.queryByRole('button', { name: 'עריכה' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'מחיקה' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByText('כבר הכנתי')).toBeInTheDocument()
    // Without pictures, no empty media section; without a comparison, no link to one.
    expect(screen.queryByRole('heading', { name: 'תמונות וסרטונים' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'מהמקור למתכון' })).not.toBeInTheDocument()
  })

  it('beside its source: the original, the saved recipe, the kept draft and what review changed', async () => {
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, DRINK)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))

    expect(screen.getByRole('heading', { level: 2, name: DRINK })).toHaveFocus()
    expect(window.location.hash).toBe('#/recipes/6/source')
    expect(screen.getByText(/טקסט שהודבק ביד, בלי קישור למקור/)).toBeInTheDocument()
    expect(screen.getByText(/מודל שרץ על המחשב שלי דרך Ollama/)).toHaveTextContent('qwen3:8b')
    const original = screen.getByRole('region', { name: 'הטקסט המקורי' })
    expect(original).toHaveTextContent('הגירסה שלי:')
    const saved = within(screen.getByRole('region', { name: 'המתכון השמור' }))
    expect(saved.getByText('חצי', { selector: 'mark' })).toBeInTheDocument()
    // The model's suggestion from the kept draft, beside the saved category.
    const [before, after] = within(screen.getByRole('region', { name: 'סיווג' })).getAllByRole('definition')
    expect(before).toHaveTextContent('קטגוריה ראשית: לא מסווגבטיוטה של הייבוא המקורי, מ-20 באוקטובר 2026.')
    expect(after).toHaveTextContent('קטגוריה ראשית: משקאותבמתכון השמור.')

    const record = within(screen.getByRole('region', { name: /הטיוטה של הייבוא/ }))
    expect(record.getByText(/לא מופיעה כך בטקסט המקורי/)).toBeInTheDocument()
    expect(record.getByText('קטגוריה')).toBeInTheDocument()
    expect(record.getByText('חצי תמר מג׳ hollow · כמות: חצי')).toHaveClass('diff-removed')
    expect(record.getByText('חצי תמר מג׳הול · כמות: חצי')).toHaveClass('diff-added')
    expect(record.getByText(/ללא שינוי: כותרת, כמות מנות, אופן ההכנה, הערות/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'חזרה למתכון' }))
    expect(screen.getByRole('heading', { level: 2, name: DRINK })).toBeInTheDocument()
    expect(window.location.hash).toBe('#/recipes/6')
  })

  it('says so when no copy of the draft was kept, instead of showing one', async () => {
    const withoutDemonstration = { ...notebook, recipes: notebook.recipes.map((r) => (r.id === 12 ? { ...r, processing: { draft: null } } : r)) }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(withoutDemonstration), { status: 200 })))
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, TORTE)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    expect(screen.getByText(/כיתוב של פוסט באינסטגרם/)).toHaveTextContent('ריטה קדוש')
    expect(screen.getByRole('link', { name: 'לפוסט המקורי' })).toHaveAttribute('href', 'https://www.instagram.com/p/Cm1mCdCpSzJ/')
    expect(screen.getByText(/נשמר לאחרונה 3 דקות אחרי הייבוא/)).toBeInTheDocument()
    const record = within(screen.getByRole('region', { name: /הטיוטה של הייבוא/ }))
    expect(record.getByText('הטיוטה של הייבוא המקורי לא נשמרה.')).toBeInTheDocument()
    expect(record.queryByText('מה השתנה בבדיקה')).not.toBeInTheDocument()
    const classification = within(screen.getByRole('region', { name: 'סיווג' }))
    expect(classification.getByText('ההצעה של הייבוא המקורי לא נשמרה.')).toBeInTheDocument()
    expect(classification.getAllByRole('definition')[1]).toHaveTextContent('קטגוריה ראשית: קינוחיםסוג הקינוח: לא צויןבמתכון השמור.')
  })

  it('a recorded classification check is the suggestion of a fresh run, never of the original import', async () => {
    const answer = { category: desserts, subcategory: { id: 13, name: 'טארטים ופאי' }, at: '2026-11-05T14:58:48Z' }
    const check = { run_at: '2026-11-05T14:58:21Z', model: 'qwen3:8b', answers: [answer, { ...answer, at: '2026-11-05T14:59:22Z' }] }
    const shown = { ...notebook, recipes: notebook.recipes.map((r) => (r.id === 12 ? { ...r, processing: { draft: null, classification_check: check } } : r)) }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(shown), { status: 200 })))
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, TORTE)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    const [before, after] = within(screen.getByRole('region', { name: 'סיווג' })).getAllByRole('definition')
    expect(before).toHaveTextContent(
      'קטגוריה ראשית: קינוחיםסוג הקינוח: טארטים ופאיבהרצה חדשה של הטקסט המקורי עם qwen3:8b, ב-5 בנובמבר 2026, ולא בייבוא המקורי, שהצעתו לא נשמרה. אותה בקשה נשלחה פעמיים, והתשובה זהה.',
    )
    expect(after).toHaveTextContent('סוג הקינוח: לא צויןבמתכון השמור.')
  })

  it('a classification check whose answers differ shows each of them', async () => {
    const cakes = { category: desserts, subcategory: { id: 11, name: 'עוגות' }, at: '2026-11-05T14:58:48Z' }
    const check = { run_at: '2026-11-05T14:58:21Z', model: 'qwen3:8b', answers: [cakes, { category: drinks, subcategory: null, at: '2026-11-05T14:59:22Z' }] }
    const shown = { ...notebook, recipes: notebook.recipes.map((r) => (r.id === 12 ? { ...r, processing: { draft: null, classification_check: check } } : r)) }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(shown), { status: 200 })))
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, TORTE)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    const sides = within(screen.getByRole('region', { name: 'סיווג' })).getAllByRole('definition')
    expect(sides).toHaveLength(3)
    expect(sides[0]).toHaveTextContent(/סוג הקינוח: עוגות.*תשובה 1 מתוך 2\.$/)
    expect(sides[1]).toHaveTextContent(/^קטגוריה ראשית: משקאות.*תשובה 2 מתוך 2\.$/)
  })

  it('a recorded demonstration is the comparison: the original beside its reviewed result, who did what, the draft folded', async () => {
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, TORTE)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    expect(screen.getByText('הדגמה של ייבוא מחדש באמצעות הגרסה המעודכנת של המערכת.')).toBeInTheDocument()
    const meta = document.querySelector('.demonstration-meta')
    expect(meta).toHaveTextContent(/^4 בנובמבר 2026 · qwen3:8b, מודל שרץ על המחשב שלי דרך Ollama/)
    expect(meta).toHaveTextContent('הטיוטה של הייבוא המקורי, מ-28 באוקטובר 2026, לא נשמרה')

    // One comparison: the original beside the demonstration's reviewed result, never the saved recipe in its place.
    expect(screen.getByRole('region', { name: 'הטקסט המקורי' })).toHaveTextContent('טורט וניל 🍓')
    expect(screen.queryByRole('region', { name: 'המתכון השמור' })).not.toBeInTheDocument()
    const result = screen.getByRole('region', { name: 'המתכון לאחר הבדיקה' })
    expect(result).toHaveTextContent('עוגות')
    const strawberries = within(result).getAllByRole('listitem').find((li) => li.textContent?.startsWith('תותים'))!
    expect(strawberries).toHaveTextContent('נוסף בעקבות התרעה')
    expect(strawberries.querySelector('details')).not.toHaveAttribute('open')
    await user.click(within(strawberries).getByText('נוסף בעקבות התרעה'))
    expect(strawberries.querySelector('details')).toHaveAttribute('open')
    expect(strawberries).toHaveTextContent(DECORATE)
    // Their group has no name: a display heading keeps it apart from the named group above it.
    expect(within(result).getByRole('heading', { name: 'מצרכים נוספים' })).toBeInTheDocument()

    // What review changed, each with who did it: the system by itself, the model, the review. The remark the import
    // already joined to its step is the same in the draft and the result: not listed.
    const summary = within(screen.getByRole('region', { name: 'מה קרה בהדגמה הזו' }))
    const items = summary.getAllByRole('listitem').map((li) => li.textContent)
    expect(items[0]).toMatch(/^תותיםזוהה אוטומטיתאושר בבדיקה/)
    expect(items[0]).toContain('נוסף למצרכים ללא כמות: לא הומצאה כמות.')
    expect(items[1]).toBe('סוג הקינוחהצעת המודלתוקן בבדיקההמודל הציע "טארטים ופאי"; בבדיקה זה תוקן ל"עוגות".')
    expect(items[2]).toContain('בטיוטה: לא נקבע. בבדיקה: לא קינוח בריא.')
    expect(items).toHaveLength(3)
    expect(summary.getByText('בלי תיקון בבדיקה: כותרת, כמות מנות, אופן ההכנה, הערות.')).toBeInTheDocument()
    // The classification on its own: the demonstration draft's beside the reviewed one; the healthy style is not a type.
    const [before, after] = within(screen.getByRole('region', { name: 'סיווג' })).getAllByRole('definition')
    expect(before).toHaveTextContent('קטגוריה ראשית: קינוחיםסוג הקינוח: טארטים ופאיבטיוטה של ההדגמה, מ-4 בנובמבר 2026.')
    expect(after).toHaveTextContent('קטגוריה ראשית: קינוחיםסוג הקינוח: עוגותבבדיקה שבוצעה בעת הכנת ההדגמה.')
    expect(after).not.toHaveTextContent('קינוח בריא')

    // The draft as the run saved it, its point with the action taken while preparing the demonstration: folded.
    const folded = screen.getByText('הצגת הטיוטה לפני הבדיקה').closest('details')!
    expect(folded).not.toHaveAttribute('open')
    await user.click(screen.getByText('הצגת הטיוטה לפני הבדיקה'))
    expect(folded.querySelector('.demonstration-draft')).toHaveTextContent('טארטים ופאי')
    expect(within(folded).getByText(STRAWBERRIES.message).closest('li')).toHaveTextContent(
      'בבדיקה שבוצעה בעת הכנת ההדגמה: נוסף למצרכים — תותים, ללא כמות, בלי קבוצה',
    )
    expect(within(folded).getByText('קינוחים · טארטים ופאי', { selector: '.diff-lines li' })).toHaveClass('diff-removed')

    // Read-only: nothing to add, ignore or undo; the recipe's own page is one click away.
    expect(screen.queryByRole('button', { name: /הוספת|התעלמות|טופל|ביטול/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'חזרה למתכון' }))
    expect(window.location.hash).toBe('#/recipes/12')
  })

  it('a demonstration of a recipe whose own draft a backup kept says that draft is kept apart, not that it is lost', async () => {
    const both = { ...notebook, recipes: notebook.recipes.map((r) => (r.id === 6 ? { ...r, processing: { ...r.processing!, demonstration } } : r)) }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(both), { status: 200 })))
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, DRINK)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    expect(document.querySelector('.demonstration-meta')).toHaveTextContent('הטיוטה של הייבוא המקורי, מ-20 באוקטובר 2026, שמורה בנפרד ואינה מוצגת כאן')
  })

  it('a demonstration whose draft had no points says so; only the corrected category is listed as a review change', async () => {
    const recipe = notebook.recipes.find((r) => r.id === 6)!
    const state = { title: DRINK, servings: null, healthy: null, ingredient_groups: recipe.ingredient_groups, step_groups: recipe.step_groups, notes: [] }
    const drink: Demonstration = {
      run_at: '2026-11-05T13:18:17Z',
      model: 'qwen3:8b',
      draft: { ...state, category: desserts, subcategory: { id: 14, name: 'קינוחי כוסות ומוסים' }, issues: [], saved_at: '2026-11-05T13:18:17Z' },
      reviewed: { ...state, category: drinks, subcategory: null, issues: [], resolved_issues: [], saved_at: '2026-11-05T13:19:54Z' },
    }
    const shown = { ...notebook, recipes: notebook.recipes.map((r) => (r.id === 6 ? { ...r, processing: { draft: null, demonstration: drink } } : r)) }
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(shown), { status: 200 })))
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, DRINK)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    const summary = within(screen.getByRole('region', { name: 'מה קרה בהדגמה הזו' }))
    expect(summary.getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'קטגוריההצעת המודלתוקן בבדיקההמודל הציע "קינוחים · קינוחי כוסות ומוסים"; בבדיקה זה תוקן ל"משקאות".',
    ])
    expect(summary.getByText('בלי תיקון בבדיקה: כותרת, כמות מנות, מצרכים, אופן ההכנה, הערות.')).toBeInTheDocument()
    await user.click(screen.getByText('הצגת הטיוטה לפני הבדיקה'))
    const folded = screen.getByText('הצגת הטיוטה לפני הבדיקה').closest('details')!
    expect(within(folded).getByText('הייבוא לא סימן נקודות לבדיקה.')).toBeInTheDocument()
    expect(folded.querySelectorAll('.review-issue')).toHaveLength(0)
  })

  it('the page about the project links each comparison and the repository', async () => {
    const user = userEvent.setup()
    await renderCopy()
    await user.click(screen.getByRole('button', { name: 'על הפרויקט' }))
    expect(screen.getByRole('heading', { level: 2, name: 'על מחברת המתכונים' })).toHaveFocus()
    expect(screen.getByText(/ייבוא מתכון מצילום מסך עדיין לא חלק מהמחברת/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://github.com/example/recipes' })).toHaveAttribute('href', 'https://github.com/example/recipes')
    expect(screen.getByText(/עודכן ב-/)).toHaveTextContent('2026')
    await user.click(screen.getByRole('button', { name: TORTE }))
    expect(window.location.hash).toBe('#/recipes/12/source')
  })

  it('an address of a page it does not have (editing, importing, categories) opens the gallery', async () => {
    for (const address of ['#/recipes/12/edit', '#/import', '#/new', '#/categories', '#/recipes/15/source']) {
      window.history.replaceState(null, '', `/${address}`)
      const { unmount } = render(<App />)
      await screen.findByRole('region', { name: 'המתכונים' })
      expect(window.location.hash).toBe('')
      unmount()
    }
  })

  it('when its file cannot be read, says so and can try again', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404 })))
    const user = userEvent.setup()
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('קובץ המתכונים לא נמצא (HTTP 404)')
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(notebook), { status: 200 })))
    await user.click(screen.getByRole('button', { name: 'נסו שוב' }))
    expect(await screen.findByRole('region', { name: 'המתכונים' })).toBeInTheDocument()
  })
})

describe('the notebook itself', () => {
  it('has no page about the project and no comparison page', async () => {
    vi.unstubAllEnvs()
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(url === '/api/recipes' ? notebook.recipes : notebook.categories), { status: 200 })))
    window.history.replaceState(null, '', '/#/about')
    render(<App />)
    await screen.findByRole('region', { name: 'המתכונים' })
    expect(screen.queryByRole('button', { name: 'על הפרויקט' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ייבוא מתכון/ })).toBeInTheDocument()
    act(() => {
      window.history.replaceState(null, '', '/#/recipes/6/source')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(screen.queryByRole('heading', { name: DRINK })).not.toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })
})
