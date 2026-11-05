// The review screen's actions on an imported draft's points, as pure functions of the editor's form (no React):
// approving the line a point proposes, ignoring a point, marking one done, and undoing any of them. Each returns a
// new form; nothing reaches the notebook until the form is saved, so a failed save records no decision.
import { emptyIngredient, newKey, removeAt, type IngredientGroupForm, type IngredientRow, type RecipeForm } from './editorForm'
import type { Issue, ProposedIngredient, Resolution } from './types'

/** The line a point about an ingredient only the steps name offers. A point saved before proposals existed
 * offers the ingredient its message names, without an amount or a group. null: not such a point. */
export function proposalOf(issue: Issue): ProposedIngredient | null {
  if (issue.kind !== 'ingredient_only_in_steps') return null
  if (issue.proposed) return issue.proposed
  const named = /"([^"]+)"/.exec(issue.message)
  return named ? { text: named[1], quantity: null, group: null } : null
}

// --- Is it in the list already? The rule of backend/app/extraction/ingredient_words.py, without its synonyms ---

const PREFIXES = 'ומבלכשה'
const FINALS: Record<string, string> = { ך: 'כ', ם: 'מ', ן: 'נ', ף: 'פ', ץ: 'צ' }
const WORD = /[\p{L}\p{N}]+(?:['׳’][\p{L}\p{N}]+)*/gu
const HEBREW = /[א-ת]/

/** One spelling for comparing: no apostrophes, no final letter forms, one yod or vav where some write two. */
function key(word: string): string {
  return word
    .toLowerCase()
    .replace(/['׳’״"]/g, '')
    .replace(/[ךםןףץ]/g, (letter) => FINALS[letter])
    .replaceAll('יי', 'י')
    .replaceAll('וו', 'ו')
}

/** Singular and plural alike: "תותים" and "תות", "tomatoes" and "tomato". */
function stem(word: string): string {
  if (HEBREW.test(word)) {
    const ending = ['ימ', 'ות', 'ה'].find((end) => word.endsWith(end) && word.length - end.length >= 2)
    return ending ? word.slice(0, -ending.length) : word
  }
  if (word.endsWith('ies')) return `${word.slice(0, -3)}y`
  if (/(?:oes|ches|shes|xes|sses)$/.test(word)) return word.slice(0, -2)
  return word.endsWith('s') && !word.endsWith('ss') && word.length > 3 ? word.slice(0, -1) : word
}

/** The word, and without one or two Hebrew letters attached before it ("ובתותים" -> "בתותים", "תותים"). */
function forms(word: string): string[] {
  const all = [word]
  for (let i = 0; i < 2; i++) {
    const last = all[all.length - 1]
    if (PREFIXES.includes(last[0]) && last.length > 3) all.push(last.slice(1))
  }
  return all
}

/** The proposal's ingredient without the amount it may start with ("200 גרם שוקולד" -> "שוקולד"). */
function nameOf(proposal: ProposedIngredient): string {
  const text = proposal.text.trim()
  if (proposal.quantity === null || !text.startsWith(proposal.quantity)) return text
  return text.slice(proposal.quantity.length).trim().replace(/^(?:של|of)\s+/i, '')
}

/** Does a line of the list already name it (every word of it, in any of its forms), typed in by hand or added? */
export function listsIngredient(groups: IngredientGroupForm[], proposal: ProposedIngredient): boolean {
  const listed = new Set<string>()
  for (const row of groups.flatMap((group) => group.ingredients)) {
    for (const word of row.text.match(WORD) ?? []) {
      for (const form of forms(word)) {
        const k = key(form)
        listed.add(stem(k))
        if (HEBREW.test(k) && k.endsWith('י') && k.length > 3) listed.add(k.slice(0, -1)) // "נבטי חמניות"
      }
    }
  }
  const words = nameOf(proposal).match(WORD) ?? []
  return words.length > 0 && words.every((word) => listed.has(stem(key(word))))
}

// --- Where a line goes ----------------------------------------------------------------------------------------

/** The index of the group the line goes to: the proposal's group if the form still has one by that name; else
 * -1, the list's place for lines without a group (its last group when that has no name, or a new one at the end). */
export function targetGroup(groups: IngredientGroupForm[], group: string | null): number {
  return group === null ? -1 : groups.findIndex((candidate) => candidate.name.trim() === group)
}

function placed(groups: IngredientGroupForm[], row: IngredientRow, group: string | null): { groups: IngredientGroupForm[]; group: string | null } {
  const target = targetGroup(groups, group)
  const last = groups.length - 1
  const index = target >= 0 ? target : last >= 0 && groups[last].name.trim() === '' ? last : -1
  if (index < 0) return { groups: [...groups, { key: newKey(), name: '', ingredients: [row] }], group: null }
  const into = groups[index]
  // A group's only empty row (a draft without ingredients) gives its place to the line.
  const rows = into.ingredients.filter((existing) => existing.text.trim() !== '' || existing.quantity.trim() !== '')
  return {
    groups: groups.map((existing, i) => (i === index ? { ...into, ingredients: [...rows, row] } : existing)),
    group: target >= 0 ? group : null,
  }
}

// --- The actions ----------------------------------------------------------------------------------------------

/** Adds the line the point proposes, labeled as added in review with the sentence it comes from, and resolves the
 * point as "added" with the line as placed. Nothing happens when the list already names it, or the point offers none. */
export function addProposed(form: RecipeForm, index: number): RecipeForm {
  const issue = form.issues[index]
  const proposal = issue === undefined ? null : proposalOf(issue)
  if (proposal === null || listsIngredient(form.ingredient_groups, proposal)) return form
  const row: IngredientRow = {
    key: newKey(),
    text: proposal.text,
    quantity: proposal.quantity ?? '',
    derivedFrom: issue.quote ?? proposal.text,
    addedInReview: true,
  }
  const { groups, group } = placed(form.ingredient_groups, row, proposal.group)
  const { key: _key, ...point } = issue
  return {
    ...form,
    ingredient_groups: groups,
    issues: removeAt(form.issues, index),
    resolved: [...form.resolved, { ...point, proposed: { ...proposal, group }, resolution: 'added', key: newKey(), saved: false }],
  }
}

/** Ignores the point ("dismissed", for this point of this recipe only) or marks it done ("handled"); the form's
 * content is not changed. */
export function resolvePoint(form: RecipeForm, index: number, resolution: Exclude<Resolution, 'added'>): RecipeForm {
  const issue = form.issues[index]
  if (issue === undefined) return form
  const { key: _key, ...point } = issue
  return { ...form, issues: removeAt(form.issues, index), resolved: [...form.resolved, { ...point, resolution, key: newKey(), saved: false }] }
}

/** Opens the point again. For an addition, its line leaves the list too, if it is still as it was added (a line you
 * changed since stays, and the open point then says the list has it). */
export function undoResolved(form: RecipeForm, index: number): RecipeForm {
  const entry = form.resolved[index]
  if (entry === undefined) return form
  const { key: _key, saved: _saved, resolution, ...point } = entry
  let groups = form.ingredient_groups
  if (resolution === 'added' && point.proposed) {
    const added = point.proposed
    const same = (row: IngredientRow) =>
      row.addedInReview && row.text.trim() === added.text && row.quantity.trim() === (added.quantity ?? '') && row.derivedFrom === (point.quote ?? added.text)
    const at = groups.findIndex((group) => group.ingredients.some(same))
    if (at >= 0) {
      const drop = groups[at].ingredients.findIndex(same)
      const rows = groups[at].ingredients.filter((_, i) => i !== drop)
      groups =
        rows.length === 0 && groups[at].name.trim() === ''
          ? removeAt(groups, at) // the group the line was put in alone
          : groups.map((group, i) => (i === at ? { ...group, ingredients: rows.length > 0 ? rows : [emptyIngredient()] } : group))
    }
  }
  return { ...form, ingredient_groups: groups, issues: [...form.issues, { ...point, key: newKey() }], resolved: removeAt(form.resolved, index) }
}
