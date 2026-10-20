// Every call the page makes to the backend. Components import these functions instead of
// calling fetch themselves, so request details and error handling live in one place.
//
// The paths start with /api: in development Vite forwards them to FastAPI (vite.config.ts).
import type { Category, Recipe, RecipeInput } from './types'

/** Any failed request: an error response from the API, or no answer at all. */
export class ApiError extends Error {
  /** HTTP status; 0 when the server could not be reached. */
  readonly status: number
  /** The API's stable error code, e.g. "recipe_not_found" or "invalid_request". */
  readonly code: string
  /** Extra data from the API, e.g. the list of invalid fields for "invalid_request". */
  readonly details: unknown

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

// `async` functions return a Promise: a value that arrives later. `await` waits for it
// without freezing the page.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'network_error', 'אין חיבור לשרת. ודאו שהשרת (uvicorn) פועל ונסו שוב.')
  }
  if (response.status === 204) {
    return undefined as T // "No Content": e.g. after a delete
  }
  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    // The API's single error format: {"error": {"code", "message", "details"}}.
    const error = (body as { error?: { code?: string; message?: string; details?: unknown } } | null)?.error
    if (error?.code !== undefined) {
      throw new ApiError(response.status, error.code, error.message ?? '', error.details ?? null)
    }
    // No JSON error body: typically the backend is not running and the Vite proxy answered.
    throw new ApiError(response.status, 'server_unavailable', `השרת לא ענה כמצופה (HTTP ${response.status}). ודאו שהשרת פועל.`)
  }
  return body as T
}

/** A message for the page about any failed call. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'אירעה שגיאה לא צפויה. נסו שוב.'
  }
  switch (error.code) {
    case 'network_error':
    case 'server_unavailable':
      return error.message // already written for the page, in request() above
    case 'recipe_not_found':
      return 'המתכון לא נמצא. ייתכן שנמחק בחלון אחר; רעננו את הדף.'
    case 'forbidden_origin':
      return 'השרת דחה את השינוי כי הדף לא נפתח מהכתובת הצפויה. פתחו את המחברת בכתובת http://localhost:5173'
    default:
      return `הפעולה נכשלה: ${error.message}`
  }
}

export function listRecipes(): Promise<Recipe[]> {
  return request('/api/recipes')
}

export function listCategories(): Promise<Category[]> {
  return request('/api/categories')
}

export function createRecipe(input: RecipeInput): Promise<Recipe> {
  return request('/api/recipes', { method: 'POST', body: JSON.stringify(input) })
}

export function updateRecipe(id: number, input: RecipeInput): Promise<Recipe> {
  return request(`/api/recipes/${id}`, { method: 'PUT', body: JSON.stringify(input) })
}

export function deleteRecipe(id: number): Promise<void> {
  return request(`/api/recipes/${id}`, { method: 'DELETE' })
}
