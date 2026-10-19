// The recipe data contract, mirroring backend/app/schemas.py.
// The API sends exactly these field names (snake_case) and uses null for "no value".

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

export type SourceKind = 'instagram' | 'website' | 'screenshot' | 'text'

export interface Source {
  kind: SourceKind
  url: string | null
  /** Attribution as given by the source; the first is the main author. Empty when unknown. */
  creators: string[]
}

export interface Recipe {
  id: number
  title: string
  /** null: not classified yet. */
  category: CategoryRef | null
  subcategory: CategoryRef | null
  servings: string | null
  ingredient_groups: IngredientGroup[]
  step_groups: StepGroup[]
  notes: string[]
  sources: Source[]
  /** ISO 8601 date and time with a time zone, e.g. "2026-10-19T08:00:00Z". */
  created_at: string
  updated_at: string
}
