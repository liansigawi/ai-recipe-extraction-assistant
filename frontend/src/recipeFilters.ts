// Search and filters for the recipe list: plain functions, no React, so they are easy to test.
// Everything runs on the recipes the page already has; no request and no model is involved.
import type { Recipe } from './types'

/** Which category to show: every recipe, the unclassified ones, a top-level category (with all its
 * subcategories), or one subcategory. */
export type CategoryFilter =
  | { kind: 'all' }
  | { kind: 'unclassified' }
  | { kind: 'category'; id: number }
  | { kind: 'subcategory'; id: number }

export type StatusFilter = 'all' | 'saved' | 'draft'

export interface RecipeFilters {
  text: string
  category: CategoryFilter
  status: StatusFilter
}

export const NO_FILTERS: RecipeFilters = { text: '', category: { kind: 'all' }, status: 'all' }

export function isFiltering(filters: RecipeFilters): boolean {
  return normalizeForSearch(filters.text) !== '' || filters.category.kind !== 'all' || filters.status !== 'all'
}

// Invisible direction marks, which copied Hebrew text often carries.
const BIDI_MARKS = /[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g
// Apostrophes, geresh and gershayim: "ג'ינג'ר", "ג׳ינג׳ר" and "גינגר" are found alike, and "ש״ש" as "שש".
const QUOTES = /['׳`´‘’"״“”]/g

/** Text as compared for search: no niqqud or accents, no invisible marks or quote marks, lower case,
 * single spaces. */
export function normalizeForSearch(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/\p{M}/gu, '') // niqqud and accents are separate marks after NFKD
    .replace(BIDI_MARKS, '')
    .replace(QUOTES, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim()
}

/** The words of a search found in the recipe's title or ingredient lines: every word, anywhere
 * ("שוקולד מריר" finds "200 גרם שוקולד מריר"; "תפוח" finds "תפוחים"). */
function matchesText(recipe: Recipe, words: string[]): boolean {
  if (words.length === 0) return true
  const lines = recipe.ingredient_groups.flatMap((group) => group.ingredients.map((item) => item.text))
  const searchable = normalizeForSearch([recipe.title, ...lines].join('\n'))
  return words.every((word) => searchable.includes(word))
}

function matchesCategory(recipe: Recipe, filter: CategoryFilter): boolean {
  switch (filter.kind) {
    case 'all':
      return true
    case 'unclassified':
      return recipe.category === null
    case 'category':
      return recipe.category?.id === filter.id // with or without a subcategory
    case 'subcategory':
      return recipe.subcategory?.id === filter.id
  }
}

export function filterRecipes(recipes: Recipe[], filters: RecipeFilters): Recipe[] {
  const words = normalizeForSearch(filters.text).split(' ').filter((word) => word !== '')
  return recipes.filter(
    (recipe) =>
      (filters.status === 'all' || recipe.status === filters.status) &&
      matchesCategory(recipe, filters.category) &&
      matchesText(recipe, words),
  )
}

/** The category filter as a <select> value, and back. */
export function categoryFilterValue(filter: CategoryFilter): string {
  if (filter.kind === 'all') return 'all'
  if (filter.kind === 'unclassified') return 'none'
  return `${filter.kind === 'category' ? 'c' : 's'}:${filter.id}`
}

export function categoryFilterFrom(value: string): CategoryFilter {
  if (value === 'none') return { kind: 'unclassified' }
  const [kind, id] = value.split(':')
  if ((kind === 'c' || kind === 's') && Number.isInteger(Number(id))) {
    return { kind: kind === 'c' ? 'category' : 'subcategory', id: Number(id) }
  }
  return { kind: 'all' }
}
