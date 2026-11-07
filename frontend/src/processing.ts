// How a recipe went from its source to the saved recipe, for the public copy's comparison page. No React.
import { categoryLabel, HEALTHY_LABEL, healthyLabel } from './categoryLook'
import { ADDED_IN_REVIEW_LABEL, fromStepsLabel, ISSUE_LABELS } from './labels'
import type { Category, CategoryRef, Demonstration, IngredientGroup, Issue, KeptDraft, Recipe, ResolvedIssue, StepGroup } from './types'

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

// --- A demonstration, in a few lines ---------------------------------------------------------------------------

/** Who did it: the import by itself (its checks), the model, or the review. */
export type SummaryTag = 'detected' | 'model' | 'approved' | 'dismissed' | 'handled' | 'corrected'

export const SUMMARY_TAGS: Record<SummaryTag, string> = {
  detected: 'זוהה אוטומטית',
  model: 'הצעת המודל',
  approved: 'אושר בבדיקה',
  dismissed: 'נדחה בבדיקה',
  handled: 'טופל בבדיקה',
  corrected: 'תוקן בבדיקה',
}

export interface SummaryItem {
  topic: string
  tags: SummaryTag[]
  text: string
}

/** What review changed in a demonstration, from its record only: each point's decision, what the model chose and
 * review corrected, any other correction; and the parts review left as the import made them. What the import already
 * did right (a remark joined to its step) is the same in the draft and the result: not a change, not listed. */
export function demonstrationSummary(demo: Demonstration, categories: Category[]): { items: SummaryItem[]; unchanged: string[] } {
  const { draft, reviewed } = demo
  const items: SummaryItem[] = []
  for (const decided of reviewed.resolved_issues) {
    const named = /"([^"]+)"/.exec(decided.message)?.[1]
    if (decided.kind === 'ingredient_only_in_steps' && named !== undefined) {
      const found = `המערכת מצאה את "${named}" בהוראות ההכנה ולא ברשימת המצרכים, והציעה להוסיף את המצרך.`
      if (decided.resolution === 'added' && decided.proposed) {
        const { text, quantity } = decided.proposed
        const amount = quantity === null ? 'ללא כמות: לא הומצאה כמות.' : `עם הכמות שכתובה בהוראות, "${quantity}".`
        items.push({ topic: named, tags: ['detected', 'approved'], text: `${found} בבדיקה ההצעה אושרה, ו"${text}" נוסף למצרכים ${amount}` })
      } else {
        const outcome = decided.resolution === 'dismissed' ? 'בבדיקה הוחלט להתעלם מההתרעה, ולא נוסף דבר.' : 'בבדיקה ההתרעה סומנה כטופלה, בלי להוסיף את השורה המוצעת.'
        items.push({ topic: named, tags: ['detected', decided.resolution === 'dismissed' ? 'dismissed' : 'handled'], text: `${found} ${outcome}` })
      }
    } else if (decided.kind === 'missing_title') {
      // The model composed the title; review confirmed it or changed it (the title part says which).
      const from = decided.quote === null ? 'מתוך הטקסט' : `מתוך השורה "${decided.quote}"`
      const kept = draft.title === reviewed.title
      items.push({
        topic: ISSUE_LABELS[decided.kind],
        tags: ['model', kept ? 'approved' : 'corrected'],
        text: `לכיתוב אין שורת כותרת, והמודל הציע את "${draft.title}" ${from}. ${kept ? 'בבדיקה הכותרת אושרה כמו שהיא.' : `בבדיקה היא שונתה ל"${reviewed.title}".`}`,
      })
    } else {
      const outcome = decided.resolution === 'dismissed' ? 'בבדיקה הוחלט להתעלם ממנה.' : 'בבדיקה היא נבדקה וסומנה כטופלה.'
      items.push({ topic: ISSUE_LABELS[decided.kind], tags: ['detected', decided.resolution === 'dismissed' ? 'dismissed' : 'handled'], text: `${decided.message} ${outcome}` })
    }
  }
  if (draft.category?.id === reviewed.category?.id && draft.subcategory?.id !== reviewed.subcategory?.id) {
    const dessert = categories.find((category) => category.id === draft.category?.id)?.healthy_style === true
    items.push({
      topic: dessert ? 'סוג הקינוח' : 'תת-קטגוריה',
      tags: ['model', 'corrected'],
      text: `המודל הציע "${draft.subcategory?.name ?? 'ללא'}"; בבדיקה זה תוקן ל"${reviewed.subcategory?.name ?? 'ללא'}".`,
    })
  } else if (draft.category?.id !== reviewed.category?.id) {
    items.push({
      topic: 'קטגוריה',
      tags: ['model', 'corrected'],
      text: `המודל הציע "${categoryLabel(draft.category, draft.subcategory)}"; בבדיקה זה תוקן ל"${categoryLabel(reviewed.category, reviewed.subcategory)}".`,
    })
  }
  if ((draft.healthy ?? null) !== reviewed.healthy) {
    items.push({ topic: HEALTHY_LABEL, tags: ['corrected'], text: `בטיוטה: ${healthyLabel(draft.healthy) ?? 'לא נקבע'}. בבדיקה: ${healthyLabel(reviewed.healthy) ?? 'לא נקבע'}.` })
  }
  const { changed, unchanged } = reviewChanges(draft, reviewed)
  // Parts review changed by hand beyond the above: an ingredient change other than the lines added from points.
  const other = changed
    .filter((change) => change.part !== 'קטגוריה')
    .filter((change) => !(change.part === 'מצרכים' && change.lines.every((line) => line.kind === 'added' && line.text.endsWith(ADDED_IN_REVIEW_LABEL))))
    .map((change) => change.part)
  if (other.length > 0) {
    items.push({ topic: 'תיקונים נוספים', tags: ['corrected'], text: `בבדיקה תוקנו גם: ${other.join(', ')}. הפירוט בטיוטה שלפני הבדיקה.` })
  }
  return { items, unchanged }
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
