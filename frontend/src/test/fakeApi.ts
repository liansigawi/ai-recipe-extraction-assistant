// A stand-in for the backend in tests. It replaces the browser's fetch and answers from memory
// the way the FastAPI app does, so tests run without a server and can check what the page sent.
import { vi } from 'vitest'
import type { Category, Recipe, RecipeInput } from '../types'

export interface Call {
  method: string
  path: string
  body: unknown
}

const SAVED_AT = '2026-10-20T09:30:00Z'

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export function fakeApi(initial: { recipes: Recipe[]; categories: Category[] }) {
  let recipes = structuredClone(initial.recipes) // a deep copy: tests cannot change the shared test data
  const categories = structuredClone(initial.categories)
  let nextId = Math.max(0, ...recipes.map((recipe) => recipe.id)) + 1
  const calls: Call[] = []
  const queued: Response[] = [] // one-off answers, given before the normal ones
  let offline = false

  function stored(input: RecipeInput, id: number, createdAt: string, isSample: boolean): Recipe {
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
      is_sample: isSample,
      created_at: createdAt,
      updated_at: SAVED_AT,
    }
  }

  async function handle(path: string, init: RequestInit = {}): Promise<Response> {
    const method = init.method ?? 'GET'
    const body: unknown = typeof init.body === 'string' ? JSON.parse(init.body) : undefined
    calls.push({ method, path, body })
    if (offline) {
      throw new TypeError('Failed to fetch') // what fetch does when nothing answers
    }
    const next = queued.shift()
    if (next !== undefined) return next

    if (path === '/api/recipes' && method === 'GET') return json(200, recipes)
    if (path === '/api/categories' && method === 'GET') return json(200, categories)
    if (path === '/api/recipes' && method === 'POST') {
      const recipe = stored(body as RecipeInput, nextId++, SAVED_AT, false)
      recipes = [recipe, ...recipes]
      return json(201, recipe)
    }
    const id = Number(/^\/api\/recipes\/(\d+)$/.exec(path)?.[1])
    const existing = recipes.find((recipe) => recipe.id === id)
    if (existing === undefined) {
      return json(404, { error: { code: 'recipe_not_found', message: `There is no recipe with id ${id}.`, details: null } })
    }
    if (method === 'PUT') {
      const recipe = stored(body as RecipeInput, id, existing.created_at, existing.is_sample)
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
  }
}
