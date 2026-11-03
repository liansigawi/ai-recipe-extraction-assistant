// The recipe data contract, mirroring backend/app/schemas.py.
// The API sends exactly these field names (snake_case) and uses null for "no value".
// `interface B extends A` means "everything in A, plus these fields".

export interface CategoryRef {
  id: number
  name: string
}

export interface Ingredient {
  /** The line exactly as written, e.g. "2 כוסות אורז בסמטי". */
  text: string
  /** The amount exactly as written ("2 כוסות"), or null when the recipe gives none. */
  quantity: string | null
  /** A line the app added from the preparation (e.g. "מעט שמן לטיגון"): the sentence of the steps it comes
   * from, shown with DERIVED_LABEL. null or absent: a line of the recipe's own list, or one typed in. */
  derived_from?: string | null
}

export interface IngredientGroup {
  /** "לבצק", "למלית"; null when the recipe does not group its ingredients. */
  name: string | null
  ingredients: Ingredient[]
}

export interface StepGroup {
  /** "בסיר לחץ", "לסירופ"; null for a recipe with one plain list of steps. */
  name: string | null
  /** In order, each as written. */
  steps: string[]
}

/** How the recipe got here; 'manual' means typed in the editor. */
export type SourceKind = 'instagram' | 'website' | 'screenshot' | 'text' | 'manual'

/** Who is credited: a display name, an Instagram username (without "@"), or both. */
export interface Creator {
  name: string | null
  username: string | null
}

export interface Source {
  kind: SourceKind
  url: string | null
  /** The credit, editable: as given by the source, the first is the main author. Empty when unknown. */
  creators: Creator[]
}

/** The recipe itself: what the editor changes. */
export interface RecipeContent {
  title: string
  servings: string | null
  ingredient_groups: IngredientGroup[]
  step_groups: StepGroup[]
  notes: string[]
  sources: Source[]
}

/** 'draft': imported, not reviewed yet. 'saved': saved as a recipe. */
export type RecipeStatus = 'draft' | 'saved'

/** What an import flagged for review (backend/app/schemas.py explains each kind). */
export type IssueKind =
  | 'ingredient_only_in_steps'
  | 'unclear_text'
  | 'missing_information'
  | 'ambiguous_alternative'
  | 'multiple_recipes'
  | 'other'
  | 'missing_title'
  | 'quantity_not_in_line'
  | 'not_found_in_source'
  | 'classification_unresolved'
  | 'not_extracted'
  | 'unused_text'
  | 'invalid_reference'
  | 'caption_incomplete'
  | 'media_incomplete'

export interface Issue {
  kind: IssueKind
  /** For the person, in Hebrew. */
  message: string
  /** The exact words of the original text it is about, or null. */
  quote: string | null
}

/** The text a recipe was imported from, exactly as pasted. Read-only. */
export interface ImportedOriginal {
  /** 'text': pasted by the person; 'instagram': the caption, read from the post. */
  kind: 'text' | 'instagram' | 'website'
  text: string
  /** The model that read it; null: saved without a model. */
  model: string | null
  imported_at: string
  /** The post it came from (also for a caption pasted after reading the post failed). */
  url: string | null
  /** Which public page of the post supplied a caption read automatically. */
  /** What supplied it: a post's page or embed view (Instagram); a page's recipe data or main text (a website). */
  retrieved_from: 'post_page' | 'embed_view' | 'json_ld' | 'microdata' | 'page_text' | null
  /** Who posted it, as read from the post (never edited; the credit you edit is in the sources). */
  author: Creator | null
  coauthors: Creator[]
  /** A website's own name, as its page gives it. */
  site_name?: string | null
}

/** A file saved on this computer, served at its url. */
export interface MediaFileRef {
  id: number
  url: string
  content_type: string
  size_bytes: number
}

/** One of a recipe's pictures or videos. Changed only through the media calls, never by saving the recipe. */
export interface RecipeMediaItem {
  id: number
  kind: 'image' | 'video'
  /** 'thumbnail_only': a video that could not be saved here; its poster is, and post_url plays it. */
  status: 'saved' | 'thumbnail_only'
  file: MediaFileRef | null
  thumbnail: MediaFileRef | null
  origin: 'instagram' | 'upload' | 'website'
  post_url: string | null
  post_index: number | null
  width: number | null
  height: number | null
  is_cover: boolean
}

/** What happened to a post's media. */
export interface MediaReport {
  found: number
  saved: number
  thumbnails_only: number
  failed: number
  already_had: number
  problems: string[]
}

/** A stored recipe, as the API returns it. */
export interface Recipe extends RecipeContent {
  id: number
  /** null: not classified yet. */
  category: CategoryRef | null
  subcategory: CategoryRef | null
  /** "קינוח בריא": true, false, or null (not decided). Only a dessert has it; separate from its type (the subcategory). */
  healthy: boolean | null
  /** true for the built-in examples, which were invented for the project. */
  is_sample: boolean
  status: RecipeStatus
  /** What to check before saving a draft. */
  issues: Issue[]
  /** Whether you have cooked it. Changed only with setCooked, never by saving the recipe. */
  cooked: boolean
  /** null: typed in by hand. */
  original: ImportedOriginal | null
  /** Its pictures and videos: the post's, in the post's order, then uploads. */
  media: RecipeMediaItem[]
  /** The one shown on the card: the chosen cover, or the first with a picture. */
  cover_id: number | null
  /** ISO 8601 date and time with a time zone, e.g. "2026-10-19T08:00:00Z". */
  created_at: string
  updated_at: string
  /** The public copy only, on the few recipes chosen to show how they were made. */
  processing?: Processing | null
}

/** What the records say about how a recipe went from its source to the saved recipe (the public copy). */
export interface Processing {
  /** The import's own draft from before any review, as a backup of the database kept it; null: no copy was kept. */
  draft: KeptDraft | null
}

/** An import's draft exactly as the import saved it. */
export interface KeptDraft {
  title: string
  servings: string | null
  category: CategoryRef | null
  subcategory: CategoryRef | null
  /** Absent in an export made before the attribute existed. */
  healthy?: boolean | null
  ingredient_groups: IngredientGroup[]
  step_groups: StepGroup[]
  notes: string[]
  /** The review points the import raised. */
  issues: Issue[]
  saved_at: string
}

/** The public copy's data file, notebook.json beside the page (backend/scripts/export_public.py). */
export interface PublicNotebook {
  exported_at: string
  /** The project's code, linked from the "about" page; null: no link. */
  repository_url: string | null
  recipes: Recipe[]
  categories: Category[]
}

/** What the page sends to create or save a recipe. Categories are chosen by id only. */
export interface RecipeInput extends RecipeContent {
  category_id: number | null
  subcategory_id: number | null
  /** Only with a category whose healthy_style is true; the server refuses it otherwise. */
  healthy: boolean | null
  status: RecipeStatus
  /** The issues still open, when saving a draft. */
  issues: Issue[]
}

/** GET /api/extraction: can imports use a model right now, and which one? */
export interface ExtractionInfo {
  /** Ready: an API key is set (Claude), or Ollama runs and has the model (local). */
  configured: boolean
  provider: 'claude' | 'ollama'
  model: string
  /** true: the text stays on this computer. */
  local: boolean
  /** Why it is not ready. */
  problem: 'no_api_key' | 'ollama_unreachable' | 'ollama_model_missing' | null
}

export interface Subcategory {
  id: number
  name: string
  description: string | null
}

/** A top-level category with its subcategories (GET /api/categories). */
export interface Category extends Subcategory {
  subcategories: Subcategory[]
  /** Its recipes can be marked "קינוח בריא" (the desserts). Absent: false. */
  healthy_style?: boolean
}

/** What the page sends to create a category (POST) or to change one (PUT: no parent_id; it never changes). */
export interface CategoryInput {
  name: string
  /** What belongs in it: the model classifies new imports by it. Empty: none. */
  description: string
  /** Only when creating: the top-level category a new subcategory goes under. */
  parent_id?: number | null
}

/** A recipe that already links to the same Instagram post (a duplicate_link error lists them). */
export interface LinkedRecipe {
  id: number
  title: string
  status: RecipeStatus
}

/** A category as created or changed. */
export interface CategoryRow {
  id: number
  name: string
  description: string | null
  parent_id: number | null
}
