import { describe, expect, it } from 'vitest'
import {
  categoryFilterFrom,
  categoryFilterValue,
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

  it('turns the category filter into a select value and back', () => {
    for (const filter of [{ kind: 'all' }, { kind: 'unclassified' }, { kind: 'category', id: 3 }, { kind: 'subcategory', id: 10 }] as const) {
      expect(categoryFilterFrom(categoryFilterValue(filter))).toEqual(filter)
    }
    expect(categoryFilterFrom('nonsense')).toEqual({ kind: 'all' })
  })
})
