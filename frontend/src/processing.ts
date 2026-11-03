// How a recipe went from its source to the saved recipe, for the public copy's comparison page. No React.
import { categoryLabel, healthyLabel } from './categoryLook'
import { DERIVED_LABEL } from './labels'
import type { CategoryRef, IngredientGroup, KeptDraft, Recipe, StepGroup } from './types'

export interface LineChange {
  kind: 'removed' | 'added'
  text: string
}

/** One part of the recipe that review changed, with only the lines that differ. */
export interface PartChange {
  part: string
  lines: LineChange[]
}

/** The lines only in `before` (removed) and only in `after` (added), in order; lines in both are left out.
 * By the longest common subsequence, so one changed line is one removal and one addition, not a cascade. */
export function diffLines(before: string[], after: string[]): LineChange[] {
  // common[i][j]: how many lines before[i..] and after[j..] can keep in common.
  const common = Array.from({ length: before.length + 1 }, () => new Array<number>(after.length + 1).fill(0))
  for (let i = before.length - 1; i >= 0; i--) {
    for (let j = after.length - 1; j >= 0; j--) {
      common[i][j] = before[i] === after[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1])
    }
  }
  const changes: LineChange[] = []
  let i = 0
  let j = 0
  while (i < before.length || j < after.length) {
    if (i < before.length && j < after.length && before[i] === after[j]) {
      i++
      j++
    } else if (i < before.length && (j === after.length || common[i + 1][j] >= common[i][j + 1])) {
      changes.push({ kind: 'removed', text: before[i++] })
    } else {
      changes.push({ kind: 'added', text: after[j++] })
    }
  }
  return changes
}

// Each part as lines to compare. A group's name is a line of its own; an ingredient's line carries its
// quantity, so a quantity changed alone shows too.
function ingredientLines(groups: IngredientGroup[]): string[] {
  return groups.flatMap((group) => [
    ...(group.name !== null ? [`${group.name}:`] : []),
    ...group.ingredients.map(
      (item) =>
        `${item.text} · ${item.quantity === null ? 'ללא כמות' : `כמות: ${item.quantity}`}${item.derived_from != null ? ` · ${DERIVED_LABEL}` : ''}`,
    ),
  ])
}

// The category line, with the dessert's healthy style when it was decided.
function classification(category: CategoryRef | null, subcategory: CategoryRef | null, healthy: boolean | null | undefined): string[] {
  const style = healthyLabel(healthy)
  return [style === null ? categoryLabel(category, subcategory) : `${categoryLabel(category, subcategory)} · ${style}`]
}

function stepLines(groups: StepGroup[]): string[] {
  return groups.flatMap((group) => [...(group.name !== null ? [`${group.name}:`] : []), ...group.steps])
}

/** What review changed between the import's draft and the saved recipe, part by part. */
export function reviewChanges(draft: KeptDraft, recipe: Recipe): { changed: PartChange[]; unchanged: string[] } {
  const parts: [string, string[], string[]][] = [
    ['כותרת', [draft.title], [recipe.title]],
    ['כמות מנות', [draft.servings ?? 'לא צוין'], [recipe.servings ?? 'לא צוין']],
    ['קטגוריה', classification(draft.category, draft.subcategory, draft.healthy), classification(recipe.category, recipe.subcategory, recipe.healthy)],
    ['מצרכים', ingredientLines(draft.ingredient_groups), ingredientLines(recipe.ingredient_groups)],
    ['אופן ההכנה', stepLines(draft.step_groups), stepLines(recipe.step_groups)],
    ['הערות', draft.notes, recipe.notes],
  ]
  const changed: PartChange[] = []
  const unchanged: string[] = []
  for (const [part, before, after] of parts) {
    const lines = diffLines(before, after)
    if (lines.length === 0) unchanged.push(part)
    else changed.push({ part, lines })
  }
  return { changed, unchanged }
}

/** "פחות מדקה", "4 דקות", "שעתיים", "6 ימים": the time from one moment to a later one. */
export function elapsedText(fromIso: string, toIso: string): string {
  const minutes = Math.floor((Date.parse(toIso) - Date.parse(fromIso)) / 60_000)
  if (minutes < 1) return 'פחות מדקה'
  if (minutes < 60) return minutes === 1 ? 'דקה' : `${minutes} דקות`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return hours === 1 ? 'שעה' : hours === 2 ? 'שעתיים' : `${hours} שעות`
  const days = Math.floor(hours / 24)
  return days === 1 ? 'יום' : days === 2 ? 'יומיים' : `${days} ימים`
}
