// Every call the page makes to the backend. Components import these functions instead of
// calling fetch themselves, so request details and error handling live in one place.
//
// The paths start with /api: in development Vite forwards them to FastAPI (vite.config.ts).
import type { Category, CategoryInput, CategoryRow, ExtractionInfo, Recipe, RecipeInput } from './types'

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
    case 'category_name_taken':
      return 'כבר יש קטגוריה בשם הזה באותה רמה. בחרו שם אחר.'
    case 'invalid_parent':
      return 'אפשר להוסיף תת-קטגוריה רק לקטגוריה ראשית קיימת.'
    case 'category_not_found':
      return 'הקטגוריה לא נמצאה. ייתכן ששונתה בחלון אחר; רעננו את הדף.'
    case 'forbidden_origin':
      return 'השרת דחה את השינוי כי הדף לא נפתח מהכתובת הצפויה. פתחו את המחברת בכתובת http://localhost:5173'
    // Importing (backend/app/extraction/: claude.py for the Claude API, ollama.py for a local model).
    case 'extraction_not_configured':
      return 'לא הוגדר מפתח ל-Claude API בשרת. ההוראות ב-README, בסעיף "Connect the Claude API".'
    case 'extraction_auth_failed':
      return 'Claude API לא קיבל את המפתח. בדקו את ANTHROPIC_API_KEY בקובץ .env ונסו שוב.'
    case 'extraction_busy':
      return 'Claude עמוס כרגע. נסו שוב בעוד כמה דקות.'
    case 'extraction_unreachable':
      return 'אין חיבור ל-Claude API. בדקו את החיבור לאינטרנט ונסו שוב.'
    case 'extraction_local_unavailable':
      return 'Ollama לא פועל במחשב הזה. הפעילו את Ollama (מתפריט התחל) ונסו שוב.'
    case 'extraction_model_missing':
      return `המודל המקומי עוד לא הורד ל-Ollama (${error.message}).`
    case 'extraction_timeout':
      return 'המודל לא ענה בזמן. נסו שוב.'
    case 'extraction_refused':
    case 'extraction_incomplete':
    case 'extraction_invalid_output':
    case 'extraction_failed':
      return `המודל לא הצליח לקרוא את המתכון הפעם (${error.message}). נסו שוב.`
    case 'not_a_recipe':
      return 'לא נמצא מתכון בטקסט.'
    // Reading an Instagram post (backend/app/importers/instagram.py).
    case 'invalid_instagram_url':
      return 'זה לא נראה כמו קישור לפוסט או ל-Reel באינסטגרם. העתיקו את הכתובת מהפוסט עצמו (למשל https://www.instagram.com/p/...). קישורי שיתוף (instagram.com/share/...) עוד לא נתמכים: פתחו אותם בדפדפן והעתיקו את כתובת הפוסט.'
    case 'instagram_unavailable':
      return 'אינסטגרם אומר שהפוסט לא זמין (נמחק, פרטי, או לא זמין כרגע).'
    case 'instagram_login_required':
      return 'אינסטגרם מבקש להתחבר כדי לראות את הפוסט הזה. המחברת לא מתחברת לאינסטגרם בשמכם.'
    case 'instagram_rate_limited':
      return 'אינסטגרם מבקש להמתין לפני שקוראים פוסטים נוספים. נסו שוב מאוחר יותר.'
    case 'instagram_no_caption':
      return 'לפוסט אין כיתוב.'
    case 'instagram_caption_not_found':
      return 'דף הפוסט נטען, אבל הכיתוב לא נמצא בו.'
    case 'instagram_timeout':
      return 'אינסטגרם לא ענה בזמן.'
    case 'instagram_error':
      return 'לא הצלחנו לקרוא את הפוסט.'
    case 'instagram_caption_incomplete':
      return 'נקראה רק תצוגה מקדימה של הכיתוב, וייתכן שהיא קטועה.'
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

/** A new top-level category, or with parent_id a subcategory of one. */
export function createCategory(input: CategoryInput): Promise<CategoryRow> {
  return request('/api/categories', { method: 'POST', body: JSON.stringify(input) })
}

/** A category's new name and description: its id, parent and recipes stay. */
export function updateCategory(id: number, input: CategoryInput): Promise<CategoryRow> {
  const { name, description } = input
  return request(`/api/categories/${id}`, { method: 'PUT', body: JSON.stringify({ name, description }) })
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

export function getExtractionInfo(): Promise<ExtractionInfo> {
  return request('/api/extraction')
}

/**
 * Pasted text -> a saved draft for review. With useModel = false the text is saved without
 * Claude, to fill in by hand. Can take a minute: Claude reads the whole text.
 */
export function importText(
  text: string,
  useModel: boolean,
  from: { url?: string; possiblyIncomplete?: boolean } = {},
): Promise<Recipe> {
  // The post's address and the "preview" flag are sent only when there is one.
  const body = {
    text,
    use_model: useModel,
    ...(from.url ? { url: from.url } : {}),
    ...(from.possiblyIncomplete ? { possibly_incomplete: true } : {}),
  }
  return request('/api/imports/text', { method: 'POST', body: JSON.stringify(body) })
}

/**
 * An Instagram post's address -> its caption, read by the backend from the public post -> a saved
 * draft for review. Takes a few seconds more than pasted text. When the post cannot be read, the
 * error's details carry the address and any caption that was read (captionFrom below).
 */
export function importInstagram(url: string, useModel: boolean): Promise<Recipe> {
  return request('/api/imports/instagram', { method: 'POST', body: JSON.stringify({ url, use_model: useModel }) })
}

/** The caption an Instagram import read before it failed (a preview, or one the model found no recipe in). */
export function captionFrom(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null
  const caption = (error.details as { caption?: unknown } | null)?.caption
  return typeof caption === 'string' && caption.trim() !== '' ? caption : null
}
