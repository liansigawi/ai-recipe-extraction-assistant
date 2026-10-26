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
  kind: 'text' | 'instagram'
  text: string
  /** The model that read it; null: saved without a model. */
  model: string | null
  imported_at: string
  /** The post it came from (also for a caption pasted after reading the post failed). */
  url: string | null
  /** Which public page of the post supplied a caption read automatically. */
  retrieved_from: 'post_page' | 'embed_view' | null
  /** Who posted it, as read from the post (never edited; the credit you edit is in the sources). */
  author: Creator | null
  coauthors: Creator[]
}

/** A stored recipe, as the API returns it. */
export interface Recipe extends RecipeContent {
  id: number
  /** null: not classified yet. */
  category: CategoryRef | null
  subcategory: CategoryRef | null
  /** true for the built-in examples, which were invented for the project. */
  is_sample: boolean
  status: RecipeStatus
  /** What to check before saving a draft. */
  issues: Issue[]
  /** null: typed in by hand. */
  original: ImportedOriginal | null
  /** ISO 8601 date and time with a time zone, e.g. "2026-10-19T08:00:00Z". */
  created_at: string
  updated_at: string
}

/** What the page sends to create or save a recipe. Categories are chosen by id only. */
export interface RecipeInput extends RecipeContent {
  category_id: number | null
  subcategory_id: number | null
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
