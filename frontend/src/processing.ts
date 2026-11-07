// How a recipe went from its source to the saved recipe, for the public copy's comparison page. No React.
import { categoryLabel, healthyLabel } from './categoryLook'
import { fromStepsLabel } from './labels'
import type { CategoryRef, Demonstration, IngredientGroup, Issue, KeptDraft, Recipe, ResolvedIssue, StepGroup } from './types'

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
        `${item.text} · ${item.quantity === null ? 'ללא כמות' : `כמות: ${item.quantity}`}${item.derived_from != null ? ` · ${fromStepsLabel(item)}` : ''}`,
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

/** The parts of a recipe that review can change: the saved recipe, or a demonstration's reviewed draft. */
export type Reviewed = Pick<Recipe, 'title' | 'servings' | 'category' | 'subcategory' | 'healthy' | 'ingredient_groups' | 'step_groups' | 'notes'>

/** What review changed between the import's draft and the recipe after review, part by part. */
export function reviewChanges(draft: KeptDraft, recipe: Reviewed): { changed: PartChange[]; unchanged: string[] } {
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

/** The decision review recorded for one of the draft's points (the same kind, message and quote), or null. */
export function decisionFor(issue: Issue, resolved: ResolvedIssue[]): ResolvedIssue | null {
  return resolved.find((entry) => entry.kind === issue.kind && entry.message === issue.message && entry.quote === issue.quote) ?? null
}

// --- A demonstration: who did what ---------------------------------------------------------------------------

/** A Hebrew list: "א", "א ו-ב", "א, ב ו-ג" ("ו-" before a number, "ו" joined to a word). */
function joined(items: string[]): string {
  if (items.length <= 1) return items.join('')
  const last = items[items.length - 1]
  return `${items.slice(0, -1).join(', ')} ${/^\d/.test(last) ? 'ו-' : 'ו'}${last}`
}

function counted(count: number, one: string, many: string): string {
  return count === 1 ? one : `${count} ${many}`
}

const LEFT_OUT: Record<string, (count: number) => string> = {
  no_alternative: (count) =>
    `לא הציגה ${counted(count, 'נקודה אחת', 'נקודות')} של המודל על "או" לא ברור: בקטעים שהמודל הצביע עליהם אין "או".`,
  outside_recipe: (count) => `לא הציגה ${counted(count, 'נקודה אחת', 'נקודות')} של המודל על קטעים שהוא עצמו סימן כלא חלק מהמתכון.`,
  no_passage: (count) => `לא הציגה ${counted(count, 'נקודה אחת', 'נקודות')} של המודל שלא הצביעו על קטע בטקסט.`,
  other_check: (count) => `לא הציגה ${counted(count, 'נקודה אחת', 'נקודות')} של המודל שלא עמדו בבדיקות שלה.`,
}

/** Who raised a review point: the model (one of the points its answer raised, as the import showed it) or the
 * system's own checks. null: the record does not say (made before the model's answer was kept). */
export function pointOrigin(issue: Issue, demo: Demonstration): 'model' | 'system' | null {
  if (!demo.answer) return null
  const quoted = (passage: string | null) =>
    passage !== null && issue.quote !== null && (issue.quote === passage || (issue.quote.endsWith('…') && passage.startsWith(issue.quote.slice(0, -1))))
  const raised = demo.answer.points.some(
    (point) => point.left_out === null && point.kind === issue.kind && (point.kind === 'multiple_recipes' || quoted(point.passage)),
  )
  return raised ? 'model' : 'system'
}

/** What the model produced and what fixed rules did on their own, in a demonstration, from its record only. What
 * review changed is not here: it is the difference between the draft and the reviewed result (reviewChanges). */
export function demonstrationAccount(demo: Demonstration): { model: string[]; rules: string[] } {
  const { draft, answer } = demo
  const automatic = demo.automatic ?? []
  const keptAs = (as: 'step' | 'note') => automatic.filter((item) => item.kind === 'kept_reference' && item.kept_as === as).length
  const ingredients = draft.ingredient_groups.reduce((count, group) => count + group.ingredients.length, 0)
  const steps = draft.step_groups.reduce((count, group) => count + group.steps.length, 0) - keptAs('step')
  const notes = draft.notes.length - keptAs('note')
  const copied = [counted(ingredients, 'שורת מצרך אחת', 'שורות מצרכים'), counted(steps, 'שלב אחד', 'שלבים'), ...(notes > 0 ? [counted(notes, 'הערה אחת', 'הערות')] : [])]
  const model = [
    `סימן לכל קטע בטקסט את תפקידו: כותרת, מצרך, שלב, הערה, או לא חלק מהמתכון. לפי הסימון הועתקו מהטקסט, מילה במילה, ${joined(copied)}.`,
    draft.issues.some((issue) => issue.kind === 'missing_title')
      ? `בטקסט אין שורת כותרת, והמודל בחר בכותרת "${draft.title}".`
      : `סימן את שורת הכותרת: "${draft.title}".`,
    draft.category === null ? 'לא בחר קטגוריה אחת בבירור.' : `בחר בקטגוריה "${categoryLabel(draft.category, draft.subcategory)}".`,
  ]
  if (answer) {
    const shown = answer.points.filter((point) => point.left_out === null).length
    const all = answer.points.length
    model.push(
      all === 0
        ? 'לא סימן נקודות לבדיקה.'
        : `סימן ${counted(all, 'נקודה אחת', 'נקודות')} לבדיקה; ${shown === all ? (all === 1 ? 'היא הוצגה' : 'כולן הוצגו') : shown === 0 ? (all === 1 ? 'היא לא הוצגה' : 'אף אחת מהן לא הוצגה') : `${shown} מהן הוצגו`}.`,
    )
  }
  const rules = ['קראה את הכמות בכל שורת מצרך מתוך השורה עצמה, לפי כללים קבועים: היא מסומנת בתוצאה.']
  for (const item of automatic) {
    rules.push(
      item.kind === 'joined_remark'
        ? `צירפה את ההערה "${item.remark}" לשלב שלפניה: במקור היא חותמת את המשפט שלו, בשורה הבאה.`
        : `שמרה ${item.kept_as === 'step' ? 'כשלב' : 'כהערה'}, מילה במילה, את הקטע "${item.text}", אף שהמודל סימן אותו כלא חלק מהמתכון: הקטע מפנה למתכון נפרד, שלא כלול בטקסט ולא יובא.`,
    )
  }
  for (const [reason, sentence] of Object.entries(LEFT_OUT)) {
    const count = answer?.points.filter((point) => point.left_out === reason).length ?? 0
    if (count > 0) rules.push(sentence(count))
  }
  const own = answer ? draft.issues.filter((issue) => pointOrigin(issue, demo) === 'system').length : 0
  if (own > 0) rules.push(`סימנה ${counted(own, 'נקודה אחת', 'נקודות')} לבדיקה, בבדיקות שלה (בפירוט למטה).`)
  return { model, rules }
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
