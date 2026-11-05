import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { PublicNotebook, Recipe } from './types'

// The public, read-only copy: the same App, built with `vite build --mode public`. It reads one exported
// file (notebook.json) instead of the API, and offers nothing that changes data.

const DRINK = 'משקה טרנדי - שייק בננה תמר ואייס קפה'
const TORTE = 'טורט וניל עם קרם מסקרפונה ותותים'
const CAKE = 'עוגת קפה ושוקולד'

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
      processing: { draft: null },
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
    expect(screen.getByRole('region', { name: 'על העותק הזה' })).toHaveTextContent('עותק ציבורי לקריאה בלבד')
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
    const user = userEvent.setup()
    await renderCopy()
    await openRecipe(user, TORTE)
    await user.click(screen.getByRole('button', { name: 'מהמקור למתכון' }))
    expect(screen.getByText(/כיתוב של פוסט באינסטגרם/)).toHaveTextContent('ריטה קדוש')
    expect(screen.getByRole('link', { name: 'לפוסט המקורי' })).toHaveAttribute('href', 'https://www.instagram.com/p/Cm1mCdCpSzJ/')
    expect(screen.getByText(/נשמר לאחרונה 3 דקות אחרי הייבוא/)).toBeInTheDocument()
    const record = within(screen.getByRole('region', { name: /הטיוטה של הייבוא/ }))
    expect(record.getByText(/הטיוטה שהייבוא הפיק לא נשמרה בנפרד/)).toBeInTheDocument()
    expect(record.queryByText('מה השתנה בבדיקה')).not.toBeInTheDocument()
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
