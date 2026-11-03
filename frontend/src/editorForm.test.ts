import { describe, expect, it } from 'vitest'
import {
  emptyIngredient,
  errorsFromApi,
  formToInput,
  moveItem,
  quotedFrom,
  recipeToForm,
  removeAt,
  validateForm,
  type RecipeForm,
} from './editorForm'
import { sampleRecipes } from './test/sampleRecipes'

const filled = (overrides: Partial<RecipeForm> = {}): RecipeForm => ({ ...recipeToForm(), title: 'עוגה', ...overrides })

describe('recipeToForm and formToInput', () => {
  it('opening a stored recipe and saving it unchanged sends back exactly its content', () => {
    for (const recipe of sampleRecipes) {
      expect(formToInput(recipeToForm(recipe)).input).toEqual({
        title: recipe.title,
        category_id: recipe.category?.id ?? null,
        subcategory_id: recipe.subcategory?.id ?? null,
        healthy: recipe.healthy,
        servings: recipe.servings,
        ingredient_groups: recipe.ingredient_groups,
        step_groups: recipe.step_groups,
        notes: recipe.notes,
        sources: recipe.sources,
        status: 'saved',
        issues: [],
      })
    }
  })

  it('a new recipe starts with one empty row of each kind, which is not sent', () => {
    const form = recipeToForm()
    expect(form.ingredient_groups).toHaveLength(1)
    expect(form.step_groups).toHaveLength(1)
    expect(formToInput(form).input).toMatchObject({ ingredient_groups: [], step_groups: [], notes: [], sources: [] })
  })

  it('gives every row its own key', () => {
    const form = recipeToForm(sampleRecipes[0])
    const keys = form.ingredient_groups.flatMap((group) => [group.key, ...group.ingredients.map((row) => row.key)])
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('trims spaces at the edges, and turns empty optional fields into null', () => {
    const form = filled({ title: '  עוגה  ', servings: '   ' })
    form.ingredient_groups[0].name = ' '
    form.ingredient_groups[0].ingredients = [{ ...emptyIngredient(), text: ' 2 ביצים ', quantity: ' 2 ' }]
    expect(formToInput(form).input).toMatchObject({
      title: 'עוגה',
      servings: null,
      ingredient_groups: [{ name: null, ingredients: [{ text: '2 ביצים', quantity: '2' }] }],
    })
  })

  it('skips empty rows, and remembers which form row each sent row came from', () => {
    const form = filled()
    form.ingredient_groups[0].ingredients = [emptyIngredient(), { ...emptyIngredient(), text: '3 ביצים' }]
    const { input, pathMap } = formToInput(form)
    expect(input.ingredient_groups[0].ingredients).toEqual([{ text: '3 ביצים', quantity: null }])
    expect(pathMap['ingredient_groups.0.ingredients.0']).toBe('ingredient_groups.0.ingredients.1')
  })

  it('keeps a source that has only its kind', () => {
    const recipe = sampleRecipes[0] // its source: pasted text, no link, no names
    expect(formToInput(recipeToForm(recipe)).input.sources).toEqual([{ kind: 'text', url: null, creators: [] }])
  })

  it('splits creator names on commas', () => {
    const form = filled()
    form.sources = [{ key: 'k', kind: 'instagram', url: 'https://www.instagram.com/p/Example12345/', creators: 'אופה @baker, @partner.shop,' }]
    expect(formToInput(form).input.sources[0].creators).toEqual([
      { name: 'אופה', username: 'baker' },
      { name: null, username: 'partner.shop' },
    ])
  })
})

describe('quotedFrom: the same rule as the backend', () => {
  it.each([
    ['115 גר’ חמאה רכה', '115 גר’'],
    ['230גרם סוכר לבן', '230גרם'],
    ['4 ביצים L (טמפ׳ חדר) מופרדות', '4'],
    ['2 cups, chopped', '2 cups'],
    ['קורט מלח', 'קורט'],
  ])('accepts %s → %s', (text, quantity) => {
    expect(quotedFrom(quantity, text)).toBe(true)
  })

  it.each([
    ['200 גרם שוקולד מריר', '2'],
    ['200 גרם שוקולד מריר', '20'],
    ['1/2 כפית מלח', '1'],
    ['2.5 cups flour', '2'],
    ['115 גר’ חמאה רכה', '115 גרם'], // normalized: not as written
    ['חצי כוס (1/2) מים', '(1'], // regex characters are matched literally
  ])('refuses %s → %s', (text, quantity) => {
    expect(quotedFrom(quantity, text)).toBe(false)
  })
})

describe('validateForm', () => {
  it('accepts a recipe with only a title', () => {
    expect(validateForm(filled())).toEqual({})
  })

  it('requires a title', () => {
    expect(validateForm(filled({ title: ' ' }))).toEqual({ title: 'כתבו כותרת למתכון.' })
  })

  it('refuses a quantity without its line, and a named group without ingredients', () => {
    const form = filled()
    form.ingredient_groups = [
      { key: 'a', name: '', ingredients: [{ key: 'b', text: '', quantity: '2' }] },
      { key: 'c', name: 'לבצק', ingredients: [emptyIngredient()] },
    ]
    expect(Object.keys(validateForm(form))).toEqual(['ingredient_groups.0.ingredients.0.text', 'ingredient_groups.1'])
  })

  it('refuses links that are not web addresses', () => {
    const form = filled()
    form.sources = [{ key: 'k', kind: 'website', url: 'javascript:alert(1)', creators: '' }]
    expect(validateForm(form)).toHaveProperty(['sources.0.url'])
  })
})

describe('errorsFromApi', () => {
  it('places category errors on the category fields', () => {
    expect(errorsFromApi('unknown_category', null, {})).toHaveProperty(['category_id'])
    expect(errorsFromApi('subcategory_not_in_category', null, {})).toHaveProperty(['subcategory_id'])
    expect(errorsFromApi('healthy_not_dessert', { field: 'healthy' }, {})).toHaveProperty(['healthy'])
  })

  it('maps a validation error back to the form row it came from', () => {
    const details = [{ loc: ['body', 'ingredient_groups', 0, 'ingredients', 0, 'quantity'], msg: 'bad' }]
    const pathMap = { 'ingredient_groups.0': 'ingredient_groups.0', 'ingredient_groups.0.ingredients.0': 'ingredient_groups.0.ingredients.3' }
    expect(errorsFromApi('invalid_request', details, pathMap)).toEqual({
      'ingredient_groups.0.ingredients.3.quantity': 'השרת דחה את הערך: bad',
    })
  })

  it('returns null for errors that are not about a field', () => {
    expect(errorsFromApi('internal_error', null, {})).toBeNull()
  })
})

describe('list helpers', () => {
  it('return new lists and leave the original unchanged', () => {
    const items = ['a', 'b', 'c']
    expect(moveItem(items, 1, -1)).toEqual(['b', 'a', 'c'])
    expect(moveItem(items, 2, 1)).toBe(items) // past the end: nothing to do
    expect(removeAt(items, 0)).toEqual(['b', 'c'])
    expect(items).toEqual(['a', 'b', 'c'])
  })
})

describe('drafts and their review issues', () => {
  const issue = { kind: 'unclear_text' as const, message: 'לא ברור כמה קמח.', quote: '200 גרם קמח' }
  const draft = { ...sampleRecipes[0], status: 'draft' as const, issues: [issue] }

  it('the form keeps the open issues, each with its own key', () => {
    const form = recipeToForm(draft)
    expect(form.issues).toHaveLength(1)
    expect(form.issues[0]).toMatchObject(issue)
    expect(form.issues[0].key).toMatch(/^row-/)
  })

  it('"save draft" sends the open issues back without their keys; "save as recipe" ends the review', () => {
    const form = recipeToForm(draft)
    expect(formToInput(form, 'draft').input).toMatchObject({ status: 'draft', issues: [issue] })
    expect(formToInput(form, 'saved').input).toMatchObject({ status: 'saved', issues: [] })
  })
})

describe('an empty recipe in the editor', () => {
  it('starts with one empty ingredient row and step, which are not sent', () => {
    const empty = { ...sampleRecipes[0], ingredient_groups: [], step_groups: [] }
    const form = recipeToForm(empty)
    expect(form.ingredient_groups).toHaveLength(1)
    expect(form.ingredient_groups[0].ingredients).toHaveLength(1)
    expect(form.step_groups[0].steps).toHaveLength(1)
    expect(formToInput(form).input).toMatchObject({ ingredient_groups: [], step_groups: [] })
  })
})
