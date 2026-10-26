// A stand-in for the backend in tests. It replaces the browser's fetch and answers from memory
// the way the FastAPI app does, so tests run without a server and can check what the page sent.
import { vi } from 'vitest'
import type { Category, ExtractionInfo, Issue, Recipe, RecipeInput } from '../types'

export interface Call {
  method: string
  path: string
  body: unknown
}

const SAVED_AT = '2026-10-20T09:30:00Z'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** What the fake import returns for a pasted text: by default, built from its first two lines. */
export type DraftMaker = (text: string, useModel: boolean) => Partial<Recipe>

export const AMBIGUOUS: Issue = {
  kind: 'classification_unresolved',
  message: 'לא ברור לאיזו קטגוריה המתכון שייך: "קינוחים", "ארוחות קלילות". בחרו בעצמכם, או השאירו לא מסווג.',
  quote: null,
}

/** The caption the fake backend "reads" from any Instagram post. */
export const INSTAGRAM_CAPTION = 'עוגת לימון של סבתא 🍋\n3 ביצים\nמערבבים ואופים 40 דקות.\n#עוגה'

function defaultDraft(text: string, useModel: boolean): Partial<Recipe> {
  const lines = text.split('\n').map((line) => line.trim()).filter((line) => line !== '')
  return {
    title: lines[0] ?? 'מתכון ללא כותרת',
    ingredient_groups: useModel && lines[1] ? [{ name: null, ingredients: [{ text: lines[1], quantity: null }] }] : [],
    issues: useModel
      ? [AMBIGUOUS, { kind: 'unclear_text', message: 'לא ברור כמה קמח.', quote: lines[1] ?? null }]
      : [{ kind: 'not_extracted', message: 'הטקסט נשמר בלי עיבוד.', quote: null }],
  }
}

export function fakeApi(initial: {
  recipes: Recipe[]
  categories: Category[]
  extraction?: ExtractionInfo
  draftFor?: DraftMaker
}) {
  let recipes = structuredClone(initial.recipes) // a deep copy: tests cannot change the shared test data
  const categories = structuredClone(initial.categories)
  let extraction: ExtractionInfo = initial.extraction ?? { configured: true, provider: 'claude', model: 'claude-opus-5-5', local: false, problem: null }
  const draftFor = initial.draftFor ?? defaultDraft
  let nextId = Math.max(0, ...recipes.map((recipe) => recipe.id)) + 1
  let nextCategoryId = Math.max(0, ...categories.flatMap((c) => [c.id, ...c.subcategories.map((s) => s.id)])) + 1
  const calls: Call[] = []
  const queued: Response[] = [] // one-off answers, given before the normal ones
  let offline = false
  let gate: Promise<void> | null = null // holds the next request back until released

  function stored(input: RecipeInput, id: number, createdAt: string, existing?: Recipe): Recipe {
    const category = categories.find((option) => option.id === input.category_id)
    return {
      id,
      title: input.title,
      category: category === undefined ? null : { id: category.id, name: category.name },
      subcategory: null,
      servings: input.servings,
      ingredient_groups: input.ingredient_groups,
      step_groups: input.step_groups,
      notes: input.notes,
      sources: input.sources,
      is_sample: existing?.is_sample ?? false,
      status: input.status,
      issues: input.issues,
      original: existing?.original ?? null, // like the real API: a save never changes the original
      created_at: createdAt,
      updated_at: SAVED_AT,
    }
  }

  async function handle(path: string, init: RequestInit = {}): Promise<Response> {
    const method = init.method ?? 'GET'
    const body: unknown = typeof init.body === 'string' ? JSON.parse(init.body) : undefined
    calls.push({ method, path, body })
    if (gate !== null) {
      const waitFor = gate
      gate = null
      await waitFor
    }
    if (offline) {
      throw new TypeError('Failed to fetch') // what fetch does when nothing answers
    }
    const next = queued.shift()
    if (next !== undefined) return next

    if (path === '/api/recipes' && method === 'GET') return json(200, recipes)
    if (path === '/api/categories' && method === 'GET') return json(200, categories)
    if (path === '/api/categories' && method === 'POST') {
      const { name, description, parent_id: parentId } = body as { name: string; description: string; parent_id: number | null }
      const siblings = parentId == null ? categories : (categories.find((c) => c.id === parentId)?.subcategories ?? [])
      if (siblings.some((c) => c.name === name.trim())) {
        return json(409, { error: { code: 'category_name_taken', message: 'Taken.', details: { field: 'name' } } })
      }
      const row = { id: nextCategoryId++, name: name.trim(), description: description.trim() || null }
      if (parentId == null) categories.push({ ...row, subcategories: [] })
      else categories.find((c) => c.id === parentId)?.subcategories.push(row)
      return json(201, { ...row, parent_id: parentId ?? null })
    }
    const categoryId = Number(/^\/api\/categories\/(\d+)$/.exec(path)?.[1])
    if (categoryId && method === 'PUT') {
      const { name, description } = body as { name: string; description: string }
      const all = [...categories, ...categories.flatMap((c) => c.subcategories)]
      const row = all.find((c) => c.id === categoryId)
      if (row === undefined) return json(404, { error: { code: 'category_not_found', message: 'No.', details: null } })
      row.name = name.trim()
      row.description = description.trim() || null
      // Like the real API, recipes show their category's current name.
      recipes = recipes.map((recipe) => ({
        ...recipe,
        category: recipe.category?.id === categoryId ? { id: categoryId, name: row.name } : recipe.category,
        subcategory: recipe.subcategory?.id === categoryId ? { id: categoryId, name: row.name } : recipe.subcategory,
      }))
      return json(200, { id: row.id, name: row.name, description: row.description, parent_id: null })
    }
    if (path === '/api/extraction' && method === 'GET') return json(200, extraction)
    if (path === '/api/recipes' && method === 'POST') {
      const recipe = stored(body as RecipeInput, nextId++, SAVED_AT)
      recipes = [recipe, ...recipes]
      return json(201, recipe)
    }
    if (path === '/api/imports/text' && method === 'POST') {
      const { text, use_model: useModel } = body as { text: string; use_model: boolean }
      if (useModel && !extraction.configured) {
        return json(503, { error: { code: 'extraction_not_configured', message: 'No key.', details: null } })
      }
      const draft: Recipe = {
        id: nextId++,
        title: 'טיוטה',
        category: null,
        subcategory: null,
        servings: null,
        ingredient_groups: [],
        step_groups: [],
        notes: [],
        sources: [{ kind: 'text', url: null, creators: [] }],
        is_sample: false,
        status: 'draft',
        issues: [],
        original: {
          kind: 'text',
          text,
          model: useModel ? extraction.model : null,
          imported_at: SAVED_AT,
          url: (body as { url?: string }).url ?? null,
          retrieved_from: null,
          author: null,
          coauthors: [],
        },
        created_at: SAVED_AT,
        updated_at: SAVED_AT,
        ...draftFor(text, useModel),
      }
      recipes = [draft, ...recipes]
      return json(201, draft)
    }
    if (path === '/api/imports/instagram' && method === 'POST') {
      // Reads every post as INSTAGRAM_CAPTION, unless a test queued another answer (answerNextWith).
      const { url, use_model: useModel } = body as { url: string; use_model: boolean }
      const draft: Recipe = {
        id: nextId++,
        title: 'טיוטה',
        category: null,
        subcategory: null,
        servings: null,
        ingredient_groups: [],
        step_groups: [],
        notes: [],
        sources: [{ kind: 'instagram', url, creators: [{ name: 'אופה ביתית', username: 'baker' }] }],
        is_sample: false,
        status: 'draft',
        issues: [],
        original: {
          kind: 'instagram',
          text: INSTAGRAM_CAPTION,
          model: useModel ? extraction.model : null,
          imported_at: SAVED_AT,
          url,
          retrieved_from: 'post_page',
          author: { name: 'אופה ביתית', username: 'baker' },
          coauthors: [],
        },
        created_at: SAVED_AT,
        updated_at: SAVED_AT,
        ...draftFor(INSTAGRAM_CAPTION, useModel),
      }
      recipes = [draft, ...recipes]
      return json(201, draft)
    }
    const id = Number(/^\/api\/recipes\/(\d+)$/.exec(path)?.[1])
    const existing = recipes.find((recipe) => recipe.id === id)
    if (existing === undefined) {
      return json(404, { error: { code: 'recipe_not_found', message: `There is no recipe with id ${id}.`, details: null } })
    }
    if (method === 'PUT') {
      const recipe = stored(body as RecipeInput, id, existing.created_at, existing)
      recipes = recipes.map((item) => (item.id === id ? recipe : item))
      return json(200, recipe)
    }
    if (method === 'DELETE') {
      recipes = recipes.filter((item) => item.id !== id)
      return new Response(null, { status: 204 })
    }
    return json(405, { error: { code: 'method_not_allowed', message: 'Method Not Allowed', details: null } })
  }

  vi.stubGlobal('fetch', vi.fn(handle)) // undone after each test (test/setup.ts)

  return {
    calls,
    /** Requests that change data: everything except GET. */
    changes: () => calls.filter((call) => call.method !== 'GET'),
    recipes: () => recipes,
    setOffline(value: boolean) {
      offline = value
    },
    answerNextWith(status: number, body: unknown) {
      queued.push(json(status, body))
    },
    /** What GET /api/extraction answers from now on, e.g. after Ollama was started. */
    setExtraction(info: ExtractionInfo) {
      extraction = info
    },
    /** The next request waits until the returned function is called: a slow answer. */
    holdNext(): () => void {
      let release = () => {}
      gate = new Promise<void>((resolve) => {
        release = resolve
      })
      return release
    },
  }
}
