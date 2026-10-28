import { describe, expect, it } from 'vitest'
import {
  cookedCounts,
  filterRecipes,
  isFiltering,
  NO_FILTERS,
  normalizeForSearch,
  type RecipeFilters,
} from './recipeFilters'
import { sampleRecipes } from './test/sampleRecipes'
import type { Recipe } from './types'

// The four samples (cake: desserts; chicken: cooking; pizza: light meals; granola: unclassified), the
// cake in the subcategory 10 "קינוחים רגילים", and a dessert draft with no subcategory.
const [cake, chicken, pizza, granola] = sampleRecipes
const recipes: Recipe[] = [
  { ...cake, subcategory: { id: 10, name: 'קינוחים רגילים' } },
  chicken,
  pizza,
  granola,
  { ...cake, id: 9, title: 'כדורי תמרים', status: 'draft', subcategory: null,
    ingredient_groups: [{ name: null, ingredients: [{ text: 'כוס תמרים מג׳הול', quantity: 'כוס' }] }] },
]
const titles = (filters: Partial<RecipeFilters>) => filterRecipes(recipes, { ...NO_FILTERS, ...filters }).map((r) => r.title)

describe('normalizing text for search', () => {
  it('ignores niqqud, invisible marks, quote marks, case and extra spaces', () => {
    expect(normalizeForSearch('שׁוֹקוֹלָד')).toBe('שוקולד')
    expect(normalizeForSearch('\u200fג׳ינג׳ר')).toBe(normalizeForSearch("ג'ינג'ר"))
    expect(normalizeForSearch("ג'ינג'ר")).toBe('גינגר')
    expect(normalizeForSearch('  Rolled   OATS ')).toBe('rolled oats')
    expect(normalizeForSearch('מ״ל')).toBe('מל')
  })
})

describe('filtering recipes', () => {
  it('without a search or filter, keeps every recipe', () => {
    expect(titles({})).toHaveLength(5)
    expect(isFiltering(NO_FILTERS)).toBe(false)
    expect(isFiltering({ ...NO_FILTERS, text: '   ' })).toBe(false)
  })

  it('finds a word in the title or in an ingredient line', () => {
    expect(titles({ text: 'פיצה' })).toEqual(['פיצה מבצק יוגורט'])
    expect(titles({ text: 'כורכום' })).toEqual(['עוף בסיר עם אורז'])
    expect(titles({ text: 'oats' })).toEqual(['Oat and Date Granola Bars'])
  })

  it('needs every word of the search, anywhere, and part of a word is enough', () => {
    expect(titles({ text: 'שוקולד חמאה' })).toEqual(['עוגת שוקולד עם גנאש'])
    expect(titles({ text: 'שוקולד אורז' })).toEqual([])
    expect(titles({ text: 'מג׳הול' })).toEqual(['כדורי תמרים'])
    expect(titles({ text: 'מגהול' })).toEqual(['כדורי תמרים']) // without the geresh too
  })

  it('a top-level category includes its subcategories and its recipes without one', () => {
    expect(titles({ category: { kind: 'category', id: 1 } })).toEqual(['עוגת שוקולד עם גנאש', 'כדורי תמרים'])
  })

  it('a subcategory narrows the list', () => {
    expect(titles({ category: { kind: 'subcategory', id: 10 } })).toEqual(['עוגת שוקולד עם גנאש'])
  })

  it('finds the unclassified recipes', () => {
    expect(titles({ category: { kind: 'unclassified' } })).toEqual(['Oat and Date Granola Bars'])
  })

  it('shows saved recipes only, or drafts only', () => {
    expect(titles({ status: 'draft' })).toEqual(['כדורי תמרים'])
    expect(titles({ status: 'saved' })).toHaveLength(4)
  })

  it('combines the search with the filters', () => {
    expect(titles({ text: 'תמרים', category: { kind: 'category', id: 1 }, status: 'draft' })).toEqual(['כדורי תמרים'])
    expect(titles({ text: 'תמרים', status: 'saved' })).toEqual([])
  })

})

describe('already cooked', () => {
  // The cake and the pizza are marked as cooked; nothing else is.
  const marked = recipes.map((recipe) => ({ ...recipe, cooked: recipe.id === cake.id || recipe.id === pizza.id }))
  const shown = (filters: Partial<RecipeFilters>) => filterRecipes(marked, { ...NO_FILTERS, ...filters }).map((r) => r.title)

  it('shows the recipes not cooked yet, or the ones cooked', () => {
    expect(shown({ cooked: 'cooked' })).toEqual([cake.title, pizza.title])
    expect(shown({ cooked: 'not_yet' })).toEqual([chicken.title, granola.title, 'כדורי תמרים'])
    expect(isFiltering({ ...NO_FILTERS, cooked: 'not_yet' })).toBe(true)
  })

  it('combines with the search, the category and the draft filter', () => {
    expect(shown({ cooked: 'not_yet', category: { kind: 'category', id: 1 } })).toEqual(['כדורי תמרים'])
    expect(shown({ cooked: 'cooked', status: 'draft' })).toEqual([])
    expect(shown({ cooked: 'cooked', text: 'פיצה' })).toEqual([pizza.title])
  })

  it('counts each choice with every other filter as it is', () => {
    expect(cookedCounts(marked, NO_FILTERS)).toEqual({ all: 5, not_yet: 3, cooked: 2 })
    expect(cookedCounts(marked, { ...NO_FILTERS, category: { kind: 'category', id: 1 }, cooked: 'cooked' })).toEqual({ all: 2, not_yet: 1, cooked: 1 })
  })
})
