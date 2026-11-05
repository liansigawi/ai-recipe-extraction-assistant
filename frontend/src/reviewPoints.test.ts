import { describe, expect, it } from 'vitest'
import { emptyIngredientGroup, formToInput, recipeToForm, type IngredientGroupForm, type RecipeForm } from './editorForm'
import { addProposed, listsIngredient, proposalOf, resolvePoint, undoResolved } from './reviewPoints'
import { sampleRecipes } from './test/sampleRecipes'
import type { Issue } from './types'

const DECORATE = 'לקשט בתותים ולהנות מביס מושלם!'
const STRAWBERRIES: Issue = {
  kind: 'ingredient_only_in_steps',
  message: 'המצרך "תותים" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
  quote: DECORATE,
  proposed: { text: 'תותים', quantity: null, group: null },
}
const CHOCOLATE: Issue = {
  kind: 'ingredient_only_in_steps',
  message: 'המצרך "שוקולד" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
  quote: 'ממיסים 200 גרם שוקולד לקרם.',
  proposed: { text: '200 גרם שוקולד', quantity: '200 גרם', group: 'לקרם' },
}

function group(name: string, ...lines: string[]): IngredientGroupForm {
  return { key: name, name, ingredients: lines.map((text) => ({ key: `${name}-${text}`, text, quantity: '', derivedFrom: null, addedInReview: false })) }
}

function draftForm(issues: Issue[], groups = [group('לבצק', '2 כוסות קמח'), group('לקרם', '200 מ"ל שמנת')]): RecipeForm {
  return { ...recipeToForm({ ...sampleRecipes[0], status: 'draft', issues }), ingredient_groups: groups }
}

const lines = (form: RecipeForm) => form.ingredient_groups.map((g) => [g.name, g.ingredients.map((row) => row.text)])

describe('the line a point offers', () => {
  it('is its proposal; a point saved before proposals offers the ingredient its message names', () => {
    expect(proposalOf(CHOCOLATE)).toEqual(CHOCOLATE.proposed)
    const older: Issue = { kind: 'ingredient_only_in_steps', message: 'המצרך "מלח" מופיע באופן ההכנה אבל לא ברשימת המצרכים.', quote: 'מפזרים מלח.' }
    expect(proposalOf(older)).toEqual({ text: 'מלח', quantity: null, group: null })
    expect(proposalOf({ kind: 'unclear_text', message: 'לא ברור "כמה".', quote: null })).toBeNull()
  })

  it('counts as listed when a line names it in any of its forms, whoever typed it', () => {
    expect(listsIngredient([group('', 'תותים טריים לקישוט')], STRAWBERRIES.proposed!)).toBe(true)
    expect(listsIngredient([group('', 'תות שדה')], STRAWBERRIES.proposed!)).toBe(true)
    expect(listsIngredient([group('', '100 גרם שוקולד מריר')], CHOCOLATE.proposed!)).toBe(true) // the amount is not its name
    expect(listsIngredient([group('', 'ריבת תות')], { text: 'תותים טריים', quantity: null, group: null })).toBe(false) // every word
    expect(listsIngredient([group('', 'קמח')], STRAWBERRIES.proposed!)).toBe(false)
  })
})

describe('adding it', () => {
  it('adds the line without an amount, labeled with its sentence, where lines without a group go, and records it', () => {
    const form = addProposed(draftForm([STRAWBERRIES]), 0)
    expect(lines(form)).toEqual([['לבצק', ['2 כוסות קמח']], ['לקרם', ['200 מ"ל שמנת']], ['', ['תותים']]])
    expect(form.ingredient_groups[2].ingredients[0]).toMatchObject({ quantity: '', derivedFrom: DECORATE, addedInReview: true })
    expect(form.issues).toEqual([])
    expect(form.resolved).toMatchObject([{ ...STRAWBERRIES, resolution: 'added', saved: false }])
    // The save sends the line and the decision together.
    const { input } = formToInput(form, 'draft')
    expect(input.ingredient_groups[2]).toEqual({ name: null, ingredients: [{ text: 'תותים', quantity: null, derived_from: DECORATE, added_in_review: true }] })
    expect(input.resolved_issues).toEqual([{ ...STRAWBERRIES, resolution: 'added' }])
  })

  it('puts it in the group the point names, with the amount the step wrote, while the form has that group', () => {
    const form = addProposed(draftForm([CHOCOLATE]), 0)
    expect(lines(form)).toEqual([['לבצק', ['2 כוסות קמח']], ['לקרם', ['200 מ"ל שמנת', '200 גרם שוקולד']]])
    expect(form.ingredient_groups[1].ingredients[1].quantity).toBe('200 גרם')
    const renamed = addProposed(draftForm([CHOCOLATE], [group('לבצק', 'קמח'), group('למלית', 'שמנת')]), 0)
    expect(lines(renamed)[2]).toEqual(['', ['200 גרם שוקולד']]) // no group by that name any more
    expect(renamed.resolved[0].proposed?.group).toBeNull() // recorded where it went
  })

  it('never adds twice: not after it was added, and not when the list already has it', () => {
    const once = addProposed(draftForm([STRAWBERRIES, { ...STRAWBERRIES, quote: 'מגישים עם תותים.' }]), 0)
    expect(addProposed(once, 0)).toBe(once) // the same ingredient, from another sentence: already in the list
    const typed = draftForm([STRAWBERRIES], [group('', '2 כוסות קמח', 'תותים')])
    expect(addProposed(typed, 0)).toBe(typed)
  })

  it('fills a draft without ingredients in place of its empty row', () => {
    const form = addProposed(draftForm([STRAWBERRIES], [emptyIngredientGroup()]), 0)
    expect(lines(form)).toEqual([['', ['תותים']]])
  })
})

describe('ignoring, marking done, and undoing', () => {
  it('ignores a point without changing the recipe, and undoing opens it again', () => {
    const before = draftForm([STRAWBERRIES])
    const ignored = resolvePoint(before, 0, 'dismissed')
    expect(ignored.ingredient_groups).toBe(before.ingredient_groups)
    expect(ignored.resolved).toMatchObject([{ resolution: 'dismissed', message: STRAWBERRIES.message }])
    const undone = undoResolved(ignored, 0)
    expect(undone.issues).toMatchObject([STRAWBERRIES])
    expect(undone.resolved).toEqual([])
  })

  it('undoing an addition takes its line out again, unless the line was changed since', () => {
    const added = addProposed(draftForm([STRAWBERRIES]), 0)
    const undone = undoResolved(added, 0)
    expect(lines(undone)).toEqual([['לבצק', ['2 כוסות קמח']], ['לקרם', ['200 מ"ל שמנת']]]) // its group went with it
    expect(undone.issues).toMatchObject([STRAWBERRIES])

    const edited: RecipeForm = { ...added, ingredient_groups: added.ingredient_groups.map((g, i) => (i === 2 ? { ...g, ingredients: [{ ...g.ingredients[0], text: 'תותים טריים' }] } : g)) }
    const kept = undoResolved(edited, 0)
    expect(lines(kept)[2]).toEqual(['', ['תותים טריים']])
    expect(listsIngredient(kept.ingredient_groups, STRAWBERRIES.proposed!)).toBe(true) // the open point now says the list has it
  })

  it('keeps the decisions in a save as a recipe too, while the open points end with the review', () => {
    const form = resolvePoint(addProposed(draftForm([STRAWBERRIES, CHOCOLATE]), 0), 0, 'handled')
    const { input } = formToInput({ ...form, issues: [...form.issues, { ...STRAWBERRIES, key: 'k' }] }, 'saved')
    expect(input.issues).toEqual([])
    expect(input.resolved_issues.map((issue) => issue.resolution)).toEqual(['added', 'handled'])
  })
})
