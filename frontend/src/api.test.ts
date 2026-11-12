import { describe, expect, it, vi } from 'vitest'
import { ApiError, createRecipe, deleteRecipe, errorMessage, importText, listRecipes } from './api'
import type { RecipeInput } from './types'

function answer(response: Response | Error) {
  const fetchMock = vi.fn(() => (response instanceof Error ? Promise.reject(response) : Promise.resolve(response)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const input: RecipeInput = {
  title: 'עוגה',
  category_id: null,
  subcategory_id: null,
  healthy: null,
  servings: null,
  ingredient_groups: [],
  step_groups: [],
  notes: [],
  sources: [],
  status: 'saved',
  issues: [],
  resolved_issues: [],
}

describe('api', () => {
  it('sends JSON with the right method and path', async () => {
    const fetchMock = answer(new Response(JSON.stringify({ id: 7 }), { status: 201 }))
    await expect(createRecipe(input)).resolves.toEqual({ id: 7 })
    expect(fetchMock).toHaveBeenCalledWith('/api/recipes', {
      method: 'POST',
      body: JSON.stringify(input),
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    })
  })

  it('treats "204 No Content" as success with no value', async () => {
    answer(new Response(null, { status: 204 }))
    await expect(deleteRecipe(3)).resolves.toBeUndefined()
  })

  it("turns the API's error format into an ApiError", async () => {
    answer(
      new Response(JSON.stringify({ error: { code: 'recipe_not_found', message: 'There is no recipe with id 3.', details: null } }), {
        status: 404,
      }),
    )
    const error = await deleteRecipe(3).catch((failure: unknown) => failure)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'recipe_not_found', message: 'There is no recipe with id 3.' })
  })

  it('explains a server that does not answer', async () => {
    answer(new TypeError('Failed to fetch'))
    await expect(listRecipes()).rejects.toMatchObject({ status: 0, code: 'network_error' })
  })

  it('explains an answer that is not from the API, e.g. the dev server when the backend is down', async () => {
    answer(new Response('', { status: 500 }))
    await expect(listRecipes()).rejects.toMatchObject({ status: 500, code: 'server_unavailable' })
  })
})

describe('errorMessage', () => {
  it('gives a message in Hebrew for each kind of failure', () => {
    expect(errorMessage(new ApiError(0, 'network_error', 'אין חיבור לשרת.'))).toBe('אין חיבור לשרת.')
    expect(errorMessage(new ApiError(404, 'recipe_not_found', 'There is no recipe with id 3.'))).toMatch(/המתכון לא נמצא/)
    expect(errorMessage(new ApiError(403, 'forbidden_origin', 'Changes are only accepted from the notebook page.'))).toMatch(
      /localhost:5173/,
    )
    expect(errorMessage(new ApiError(500, 'internal_error', 'Something went wrong on the server.'))).toBe(
      'הפעולה נכשלה: Something went wrong on the server.',
    )
    expect(errorMessage(new Error('anything'))).toBe('אירעה שגיאה לא צפויה. נסו שוב.')
  })
})

describe('importing', () => {
  it('sends the pasted text and the choice of using Claude', async () => {
    const fetchMock = answer(new Response(JSON.stringify({ id: 9, status: 'draft' }), { status: 201 }))
    await importText('חביתה\n2 ביצים', false)
    expect(fetchMock).toHaveBeenCalledWith('/api/imports/text', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ text: 'חביתה\n2 ביצים', use_model: false }),
    }))
  })

  it('explains each import failure in Hebrew', () => {
    const message = (code: string) => errorMessage(new ApiError(502, code, 'detail'))
    // Where to set the key, that only the Claude API needs one, and the local model as the other option.
    expect(message('extraction_not_configured')).toMatch(/docs\/setup\.md, בסעיף "Connect the Claude API"/)
    expect(message('extraction_not_configured')).toMatch(/נדרש רק לקריאה עם Claude API/)
    expect(message('extraction_not_configured')).toMatch(/Ollama\) לא צריך מפתח/)
    expect(message('extraction_auth_failed')).toMatch(/ANTHROPIC_API_KEY/)
    expect(message('extraction_busy')).toMatch(/עמוס/)
    expect(message('extraction_invalid_output')).toBe('המודל לא הצליח לקרוא את המתכון הפעם (detail). נסו שוב.')
    expect(message('extraction_local_unavailable')).toMatch(/Ollama לא פועל/)
    expect(message('not_a_recipe')).toBe('לא נמצא מתכון בטקסט.')
  })
})
