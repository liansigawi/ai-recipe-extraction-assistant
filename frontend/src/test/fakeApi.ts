// A stand-in for the backend in tests. It replaces the browser's fetch and answers from memory
// the way the FastAPI app does, so tests run without a server and can check what the page sent.
import { vi } from 'vitest'
import { instagramPostOf, pictureUrl } from '../media'
import type { Category, ExtractionInfo, Issue, MediaFileRef, MediaReport, Recipe, RecipeInput, RecipeMediaItem } from '../types'

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

/** What the fake backend "reads" from any recipe page (rendered from its recipe data). */
export const WEBSITE_TEXT = 'עוגת תפוזים ושקדים\n\nמצרכים\n200 גרם קמח\n2 ביצים\n\nאופן ההכנה\n1. מערבבים ואופים.'

/** The caption the fake backend "reads" from any Instagram post. */
export const INSTAGRAM_CAPTION = 'עוגת לימון של סבתא 🍋\n3 ביצים\nמערבבים ואופים 40 דקות.\n#עוגה'

export function fileRef(id: number, contentType: string): MediaFileRef {
  return { id, url: `/api/media/${id}`, content_type: contentType, size_bytes: 1000 }
}

/** A media item, an image saved from a post unless `fields` say otherwise. */
export function mediaItem(id: number, fields: Partial<RecipeMediaItem> = {}): RecipeMediaItem {
  return {
    id,
    kind: 'image',
    status: 'saved',
    file: fileRef(id * 10, 'image/jpeg'),
    thumbnail: null,
    origin: 'instagram',
    post_url: 'https://www.instagram.com/p/CLJ5G9rDi1a/',
    post_index: 0,
    width: 1080,
    height: 1350,
    is_cover: false,
    ...fields,
  }
}

/** What the fake backend "fetches" from any recipe's post: a saved video, an image, and a video kept only as its poster. */
export const POST_MEDIA: RecipeMediaItem[] = [
  mediaItem(0, { kind: 'video', file: fileRef(301, 'video/mp4'), thumbnail: fileRef(302, 'image/jpeg'), post_index: 0 }),
  mediaItem(0, { file: fileRef(303, 'image/jpeg'), post_index: 1 }),
  mediaItem(0, { kind: 'video', status: 'thumbnail_only', file: null, thumbnail: fileRef(304, 'image/jpeg'), post_index: 2 }),
]

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
  let nextMediaId = 500
  const calls: Call[] = []
  const queued: Response[] = [] // one-off answers, given before the normal ones
  let offline = false
  let gate: Promise<void> | null = null // holds the next request back until released

  /** The backend's rule: only a dessert (a category with healthy_style) is marked healthy-style or not. */
  function refused(input: RecipeInput): Response | null {
    const category = categories.find((option) => option.id === input.category_id)
    if (input.healthy !== null && input.healthy !== undefined && category?.healthy_style !== true) {
      return json(422, { error: { code: 'healthy_not_dessert', message: 'Only a dessert.', details: { field: 'healthy' } } })
    }
    return null
  }

  function stored(input: RecipeInput, id: number, createdAt: string, existing?: Recipe): Recipe {
    const category = categories.find((option) => option.id === input.category_id)
    const subcategory = category?.subcategories.find((option) => option.id === input.subcategory_id)
    return {
      id,
      title: input.title,
      category: category === undefined ? null : { id: category.id, name: category.name },
      subcategory: subcategory === undefined ? null : { id: subcategory.id, name: subcategory.name },
      healthy: input.healthy ?? null,
      servings: input.servings,
      ingredient_groups: input.ingredient_groups,
      step_groups: input.step_groups,
      notes: input.notes,
      sources: input.sources,
      is_sample: existing?.is_sample ?? false,
      status: input.status,
      issues: input.issues,
      cooked: existing?.cooked ?? false, // like the real API: a save never changes the mark...
      original: existing?.original ?? null, // ...or the original
      media: existing?.media ?? [], // ...nor the media
      cover_id: existing?.cover_id ?? null,
      created_at: createdAt,
      updated_at: SAVED_AT,
    }
  }

  /** Like the backend: the chosen cover, else the first item with a picture. */
  function withCover(recipe: Recipe): Recipe {
    const chosen = recipe.media.find((item) => item.is_cover) ?? recipe.media.find((item) => pictureUrl(item) !== null)
    return { ...recipe, cover_id: chosen?.id ?? null }
  }

  function replace(recipe: Recipe): Recipe {
    const next = withCover(recipe)
    recipes = recipes.map((item) => (item.id === next.id ? next : item))
    return next
  }

  // The media calls: an upload, the recipe's post (POST_MEDIA), the cover, a removal.
  function handleMedia(id: number, part: string, rest: string | undefined, method: string, body: unknown): Response {
    const recipe = recipes.find((item) => item.id === id)
    if (recipe === undefined) return json(404, { error: { code: 'recipe_not_found', message: 'No.', details: null } })
    if (part === 'media' && rest === undefined && method === 'POST') {
      const fileId = nextMediaId++
      const item = mediaItem(nextMediaId++, { origin: 'upload', post_url: null, post_index: null, file: fileRef(fileId, 'image/png') })
      return json(201, replace({ ...recipe, media: [...recipe.media, item] }))
    }
    if (part === 'media' && rest === 'instagram' && method === 'POST') {
      const post = instagramPostOf(recipe)
      if (post === null) return json(422, { error: { code: 'no_instagram_source', message: 'No post.', details: null } })
      const had = recipe.media.filter((item) => item.origin === 'instagram').map((item) => item.post_index)
      const added = POST_MEDIA.filter((item) => !had.includes(item.post_index)).map((item) => ({ ...item, id: nextMediaId++, post_url: post }))
      const uploads = recipe.media.filter((item) => item.origin === 'upload')
      const fromPost = [...recipe.media.filter((item) => item.origin === 'instagram'), ...added].sort((a, b) => (a.post_index ?? 0) - (b.post_index ?? 0))
      const next = replace({ ...recipe, media: [...fromPost, ...uploads] })
      const remote = added.filter((item) => item.status === 'thumbnail_only').length
      const report: MediaReport = {
        found: POST_MEDIA.length,
        saved: added.length - remote,
        thumbnails_only: remote,
        failed: 0,
        already_had: POST_MEDIA.length - added.length,
        problems: remote > 0 ? ['סרטון 3: גדול מדי (מעל 150 MB); נשמרה תמונה מתוכו.'] : [],
      }
      return json(200, { recipe: next, report })
    }
    if (part === 'cover' && method === 'PUT') {
      const mediaId = (body as { media_id: number | null }).media_id
      if (mediaId !== null && !recipe.media.some((item) => item.id === mediaId)) {
        return json(404, { error: { code: 'media_not_found', message: 'No.', details: null } })
      }
      return json(200, replace({ ...recipe, media: recipe.media.map((item) => ({ ...item, is_cover: item.id === mediaId })) }))
    }
    if (part === 'media' && rest !== undefined && method === 'DELETE') {
      const mediaId = Number(rest)
      if (!recipe.media.some((item) => item.id === mediaId)) return json(404, { error: { code: 'media_not_found', message: 'No.', details: null } })
      return json(200, replace({ ...recipe, media: recipe.media.filter((item) => item.id !== mediaId) }))
    }
    return json(405, { error: { code: 'method_not_allowed', message: 'Method Not Allowed', details: null } })
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
      const refusal = refused(body as RecipeInput)
      if (refusal !== null) return refusal
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
        healthy: null,
        servings: null,
        ingredient_groups: [],
        step_groups: [],
        notes: [],
        sources: [{ kind: 'text', url: null, creators: [] }],
        is_sample: false,
        status: 'draft',
        issues: [],
        cooked: false,
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
        media: [],
        cover_id: null,
        created_at: SAVED_AT,
        updated_at: SAVED_AT,
        ...draftFor(text, useModel),
      }
      recipes = [draft, ...recipes]
      return json(201, draft)
    }
    if (path === '/api/imports/link' && method === 'POST' && !/instagram\.com/i.test((body as { url: string }).url)) {
      // A recipe page: read as WEBSITE_TEXT, unless a test queued another answer (answerNextWith).
      const { url, use_model: useModel } = body as { url: string; use_model: boolean }
      const draft: Recipe = {
        id: nextId++,
        title: 'טיוטה',
        category: null,
        subcategory: null,
        healthy: null,
        servings: null,
        ingredient_groups: [],
        step_groups: [],
        notes: [],
        sources: [{ kind: 'website', url, creators: [{ name: 'המטבח של רותי', username: null }] }],
        is_sample: false,
        status: 'draft',
        issues: [],
        cooked: false,
        original: {
          kind: 'website',
          text: WEBSITE_TEXT,
          model: useModel ? extraction.model : null,
          imported_at: SAVED_AT,
          url,
          retrieved_from: 'json_ld',
          author: { name: 'המטבח של רותי', username: null },
          coauthors: [],
          site_name: 'המטבח של רותי',
        },
        media: [],
        cover_id: null,
        created_at: SAVED_AT,
        updated_at: SAVED_AT,
        ...draftFor(WEBSITE_TEXT, useModel),
      }
      recipes = [draft, ...recipes]
      return json(201, draft)
    }
    if ((path === '/api/imports/instagram' || path === '/api/imports/link') && method === 'POST') {
      // Reads every post as INSTAGRAM_CAPTION, unless a test queued another answer (answerNextWith).
      const { url, use_model: useModel } = body as { url: string; use_model: boolean }
      const draft: Recipe = {
        id: nextId++,
        title: 'טיוטה',
        category: null,
        subcategory: null,
        healthy: null,
        servings: null,
        ingredient_groups: [],
        step_groups: [],
        notes: [],
        sources: [{ kind: 'instagram', url, creators: [{ name: 'אופה ביתית', username: 'baker' }] }],
        is_sample: false,
        status: 'draft',
        issues: [],
        cooked: false,
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
        media: [],
        cover_id: null,
        created_at: SAVED_AT,
        updated_at: SAVED_AT,
        ...draftFor(INSTAGRAM_CAPTION, useModel),
      }
      recipes = [draft, ...recipes]
      return json(201, draft)
    }
    const cookedPath = /^\/api\/recipes\/(\d+)\/cooked$/.exec(path)
    if (cookedPath !== null && method === 'PUT') {
      const recipe = recipes.find((item) => item.id === Number(cookedPath[1]))
      if (recipe === undefined) return json(404, { error: { code: 'recipe_not_found', message: 'No.', details: null } })
      return json(200, replace({ ...recipe, cooked: (body as { cooked: boolean }).cooked }))
    }
    const mediaPath = /^\/api\/recipes\/(\d+)\/(media|cover)(?:\/(instagram|\d+))?$/.exec(path)
    if (mediaPath !== null) return handleMedia(Number(mediaPath[1]), mediaPath[2], mediaPath[3], method, body)
    const id = Number(/^\/api\/recipes\/(\d+)$/.exec(path)?.[1])
    const existing = recipes.find((recipe) => recipe.id === id)
    if (existing === undefined) {
      return json(404, { error: { code: 'recipe_not_found', message: `There is no recipe with id ${id}.`, details: null } })
    }
    if (method === 'PUT') {
      const refusal = refused(body as RecipeInput)
      if (refusal !== null) return refusal
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
