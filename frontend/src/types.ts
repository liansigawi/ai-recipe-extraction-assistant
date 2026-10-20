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

export interface Source {
  kind: SourceKind
  url: string | null
  /** Attribution as given by the source; the first is the main author. Empty when unknown. */
  creators: string[]
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

/** A stored recipe, as the API returns it. */
export interface Recipe extends RecipeContent {
  id: number
  /** null: not classified yet. */
  category: CategoryRef | null
  subcategory: CategoryRef | null
  /** true for the built-in examples, which were invented for the project. */
  is_sample: boolean
  /** ISO 8601 date and time with a time zone, e.g. "2026-10-19T08:00:00Z". */
  created_at: string
  updated_at: string
}

/** What the page sends to create or save a recipe. Categories are chosen by id only. */
export interface RecipeInput extends RecipeContent {
  category_id: number | null
  subcategory_id: number | null
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
