// The recipe editor's form state, and the pure functions around it: a recipe -> form fields,
// form fields -> what the API expects, validation, and small list helpers.
// No React here, so all of it is easy to test (editorForm.test.ts).
import { creatorsFromText, creatorToText } from './credit'
import type { Issue, Recipe, RecipeInput, RecipeStatus, SourceKind } from './types'

// --- Form state --------------------------------------------------------------------------

// Every row gets a temporary key for React's list rendering. It is never saved: the API
// only sees the order of the rows. With stable keys React knows which input belongs to
// which row when a row is removed or moved; with positions as keys, the text of a deleted
// row could stay in the input of the row that moved into its place.
let lastKey = 0
export function newKey(): string {
  lastKey += 1
  return `row-${lastKey}`
}

export interface IngredientRow {
  key: string
  text: string
  /** The amount as written in `text`; '' means the recipe gives no quantity. */
  quantity: string
}
export interface IngredientGroupForm {
  key: string
  name: string
  ingredients: IngredientRow[]
}
export interface StepRow {
  key: string
  text: string
}
export interface StepGroupForm {
  key: string
  name: string
  steps: StepRow[]
}
export interface NoteRow {
  key: string
  text: string
}
export interface SourceRow {
  key: string
  kind: SourceKind
  url: string
  /** Names separated by commas. */
  creators: string
}
/** A review issue of an imported draft; the person can mark it as handled (it is then removed). */
export interface IssueRow extends Issue {
  key: string
}

/** Every field is a string while editing, because that is what inputs hold. */
export interface RecipeForm {
  title: string
  /** '' means "not classified" (a <select> value is always a string). */
  category_id: string
  subcategory_id: string
  /** "קינוח בריא": 'yes', 'no', or '' (not decided). Only offered for a category with healthy_style. */
  healthy: '' | 'yes' | 'no'
  servings: string
  ingredient_groups: IngredientGroupForm[]
  step_groups: StepGroupForm[]
  notes: NoteRow[]
  sources: SourceRow[]
  /** Still open review issues (imported drafts only). */
  issues: IssueRow[]
}

/** Error messages by field path, e.g. "ingredient_groups.0.ingredients.2.quantity". */
export type FieldErrors = Record<string, string>

export const emptyIngredient = (): IngredientRow => ({ key: newKey(), text: '', quantity: '' })
export const emptyIngredientGroup = (): IngredientGroupForm => ({ key: newKey(), name: '', ingredients: [emptyIngredient()] })
export const emptyStep = (): StepRow => ({ key: newKey(), text: '' })
export const emptyStepGroup = (): StepGroupForm => ({ key: newKey(), name: '', steps: [emptyStep()] })
export const emptyNote = (): NoteRow => ({ key: newKey(), text: '' })
export const emptySource = (): SourceRow => ({ key: newKey(), kind: 'manual', url: '', creators: '' })

/** The form for an existing recipe, or an empty form for a new one. */
export function recipeToForm(recipe?: Recipe): RecipeForm {
  if (recipe === undefined) {
    return {
      title: '',
      category_id: '',
      subcategory_id: '',
      healthy: '',
      servings: '',
      ingredient_groups: [emptyIngredientGroup()],
      step_groups: [emptyStepGroup()],
      notes: [],
      sources: [],
      issues: [],
    }
  }
  return {
    title: recipe.title,
    category_id: recipe.category ? String(recipe.category.id) : '',
    subcategory_id: recipe.subcategory ? String(recipe.subcategory.id) : '',
    healthy: recipe.healthy === null ? '' : recipe.healthy ? 'yes' : 'no',
    servings: recipe.servings ?? '',
    // A recipe without ingredients or steps (e.g. a draft saved without Claude) starts with one
    // empty row of each, like a new recipe, ready to type into. Empty rows are never sent.
    ingredient_groups:
      recipe.ingredient_groups.length === 0
        ? [emptyIngredientGroup()]
        : recipe.ingredient_groups.map((group) => ({
            key: newKey(),
            name: group.name ?? '',
            ingredients: group.ingredients.map((ingredient) => ({
              key: newKey(),
              text: ingredient.text,
              quantity: ingredient.quantity ?? '',
            })),
          })),
    step_groups:
      recipe.step_groups.length === 0
        ? [emptyStepGroup()]
        : recipe.step_groups.map((group) => ({
            key: newKey(),
            name: group.name ?? '',
            steps: group.steps.map((text) => ({ key: newKey(), text })),
          })),
    notes: recipe.notes.map((text) => ({ key: newKey(), text })),
    sources: recipe.sources.map((source) => ({
      key: newKey(),
      kind: source.kind,
      url: source.url ?? '',
      creators: source.creators.map(creatorToText).join(', '),
    })),
    issues: recipe.issues.map((issue) => ({ ...issue, key: newKey() })),
  }
}

// --- Form -> API input ----------------------------------------------------------------------

const blank = (text: string) => text.trim() === ''
const orNull = (text: string) => (blank(text) ? null : text.trim())

/**
 * What the API expects, built from the form. Rows left completely empty are skipped
 * (they hold nothing), so `pathMap` records which form row each saved row came from:
 * an error the server reports for "ingredient_groups.0.ingredients.1" can then be shown
 * next to the right input, even if an empty row above it was skipped.
 *
 * `status` comes from the button pressed: 'saved' saves a recipe (open issues are dropped:
 * the person has reviewed it); 'draft' keeps a draft with its open issues for later.
 */
export function formToInput(
  form: RecipeForm,
  status: RecipeStatus = 'saved',
): { input: RecipeInput; pathMap: Record<string, string> } {
  const pathMap: Record<string, string> = {}

  const ingredient_groups: RecipeInput['ingredient_groups'] = []
  form.ingredient_groups.forEach((group, formGroup) => {
    const rows = group.ingredients
      .map((row, formRow) => ({ row, formRow }))
      .filter(({ row }) => !blank(row.text) || !blank(row.quantity))
    if (rows.length === 0 && blank(group.name)) return // an untouched, empty group
    const prefix = `ingredient_groups.${ingredient_groups.length}`
    pathMap[prefix] = `ingredient_groups.${formGroup}`
    rows.forEach(({ formRow }, savedRow) => {
      pathMap[`${prefix}.ingredients.${savedRow}`] = `ingredient_groups.${formGroup}.ingredients.${formRow}`
    })
    ingredient_groups.push({
      name: orNull(group.name),
      ingredients: rows.map(({ row }) => ({ text: row.text.trim(), quantity: orNull(row.quantity) })),
    })
  })

  const step_groups: RecipeInput['step_groups'] = []
  form.step_groups.forEach((group, formGroup) => {
    const rows = group.steps.map((row, formRow) => ({ row, formRow })).filter(({ row }) => !blank(row.text))
    if (rows.length === 0 && blank(group.name)) return
    const prefix = `step_groups.${step_groups.length}`
    pathMap[prefix] = `step_groups.${formGroup}`
    rows.forEach(({ formRow }, savedRow) => {
      pathMap[`${prefix}.steps.${savedRow}`] = `step_groups.${formGroup}.steps.${formRow}`
    })
    step_groups.push({ name: orNull(group.name), steps: rows.map(({ row }) => row.text.trim()) })
  })

  const notes: string[] = []
  form.notes.forEach((note, formRow) => {
    if (blank(note.text)) return
    pathMap[`notes.${notes.length}`] = `notes.${formRow}`
    notes.push(note.text.trim())
  })

  // A source row is kept even without a link or names: "pasted text" alone still says where
  // the recipe came from. The person removes a source with its own button.
  const sources: RecipeInput['sources'] = form.sources.map((source) => ({
    kind: source.kind,
    url: orNull(source.url),
    creators: creatorsFromText(source.creators),
  }))

  const input: RecipeInput = {
    title: form.title.trim(),
    category_id: form.category_id === '' ? null : Number(form.category_id),
    subcategory_id: form.subcategory_id === '' ? null : Number(form.subcategory_id),
    healthy: form.healthy === '' ? null : form.healthy === 'yes',
    servings: orNull(form.servings),
    ingredient_groups,
    step_groups,
    notes,
    sources,
    status,
    issues: status === 'draft' ? form.issues.map(({ kind, message, quote }) => ({ kind, message, quote })) : [],
  }
  return { input, pathMap }
}

// --- Validation ----------------------------------------------------------------------------------

/**
 * The quantity must be quoted from its own line, and not cut out of a longer number
 * ("2" from "200 גרם"). The same rule as the backend (backend/app/schemas.py), so the form
 * can say so before saving; the backend still checks everything.
 */
export function quotedFrom(quantity: string, text: string): boolean {
  const escaped = quantity.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const before = /^\d/.test(quantity) ? '(?<![\\d.,/])' : ''
  const after = /\d$/.test(quantity) ? '(?![\\d]|[.,/]\\d)' : ''
  return new RegExp(before + escaped + after).test(text)
}

/** Checks the form before saving. Returns an empty object when everything is fine. */
export function validateForm(form: RecipeForm): FieldErrors {
  const errors: FieldErrors = {}
  if (blank(form.title)) {
    errors.title = 'כתבו כותרת למתכון.'
  }
  form.ingredient_groups.forEach((group, g) => {
    let filled = 0
    group.ingredients.forEach((row, i) => {
      const path = `ingredient_groups.${g}.ingredients.${i}`
      if (blank(row.text) && blank(row.quantity)) return
      filled += 1
      if (blank(row.text)) {
        errors[`${path}.text`] = 'כתבו את שורת המצרך.'
      } else if (!blank(row.quantity) && !quotedFrom(row.quantity.trim(), row.text.trim())) {
        errors[`${path}.quantity`] =
          'הכמות צריכה להופיע בשורת המצרך בדיוק כפי שהיא כתובה, למשל "200 גרם" מתוך "200 גרם קמח".'
      }
    })
    if (filled === 0 && !blank(group.name)) {
      errors[`ingredient_groups.${g}`] = 'בקבוצה צריך להיות לפחות מצרך אחד.'
    }
  })
  form.step_groups.forEach((group, g) => {
    if (group.steps.every((row) => blank(row.text)) && !blank(group.name)) {
      errors[`step_groups.${g}`] = 'בקבוצה צריך להיות לפחות שלב אחד.'
    }
  })
  form.sources.forEach((source, s) => {
    if (!blank(source.url) && !/^https?:\/\/\S+$/.test(source.url.trim())) {
      errors[`sources.${s}.url`] = 'קישור צריך להתחיל ב-https:// או ב-http://'
    }
  })
  return errors
}

/** The server's errors, placed on the form fields they belong to (null: not about a field). */
export function errorsFromApi(code: string, details: unknown, pathMap: Record<string, string>): FieldErrors | null {
  if (code === 'unknown_category') {
    return { category_id: 'הקטגוריה שנבחרה לא קיימת עוד. בחרו קטגוריה אחרת.' }
  }
  if (code === 'subcategory_not_in_category') {
    return { subcategory_id: 'תת-הקטגוריה לא שייכת לקטגוריה שנבחרה.' }
  }
  if (code === 'healthy_not_dessert') {
    return { healthy: 'רק קינוח אפשר לסמן כקינוח בריא. בחרו "לא נקבע", או את הקטגוריה של הקינוחים.' }
  }
  if (code !== 'invalid_request' || !Array.isArray(details)) {
    return null
  }
  const errors: FieldErrors = {}
  for (const detail of details as { loc?: (string | number)[]; msg?: string }[]) {
    const loc = (detail.loc ?? []).filter((part, index) => !(index === 0 && part === 'body'))
    errors[toFormPath(loc.join('.'), pathMap)] = `השרת דחה את הערך: ${detail.msg ?? ''}`
  }
  return errors
}

/** Rewrites the longest saved-row prefix of `path` to the form row it came from. */
function toFormPath(path: string, pathMap: Record<string, string>): string {
  const parts = path.split('.')
  for (let length = parts.length; length > 0; length -= 1) {
    const prefix = parts.slice(0, length).join('.')
    if (prefix in pathMap) {
      return [pathMap[prefix], ...parts.slice(length)].join('.')
    }
  }
  return path
}

// --- List helpers (each returns a new array; state is never changed in place) ------------------

export function replaceAt<T>(items: T[], index: number, item: T): T[] {
  return items.map((existing, i) => (i === index ? item : existing))
}

export function removeAt<T>(items: T[], index: number): T[] {
  return items.filter((_, i) => i !== index)
}

/** Moves an item up (-1) or down (+1); a move past either end leaves the list unchanged. */
export function moveItem<T>(items: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta
  if (target < 0 || target >= items.length) return items
  const copy = [...items]
  ;[copy[index], copy[target]] = [copy[target], copy[index]]
  return copy
}
