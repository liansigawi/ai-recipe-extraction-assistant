import { describe, expect, it } from 'vitest'
import { categoryLabel, categoryLook } from './categoryLook'

const named = (name: string) => ({ id: 1, name })

describe('how a category looks', () => {
  it.each([
    ['קינוחים', 'cake', 'dessert'],
    ['ארוחות בשריות', 'pot', 'meat'],
    ['ארוחות קלילות', 'bowl', 'light'],
    ['משקאות', 'glass', 'drink'],
    ['סלטים', 'leaf', 'salad'],
    ['מרקים', 'soup', 'soup'],
    ['תוספות', 'side', 'side'],
    // A category you add looks like its kind, by its name.
    ['סלטי קיץ', 'leaf', 'salad'],
    ['מרקי חורף', 'soup', 'soup'],
    ['רטבים', 'utensils', 'other'],
  ])('%s: the %s drawing on the %s color', (name, icon, tone) => {
    expect(categoryLook(named(name))).toEqual({ icon, tone })
  })

  it('an unclassified recipe gets the notebook', () => {
    expect(categoryLook(null)).toEqual({ icon: 'book', tone: 'none' })
    expect(categoryLabel(null)).toBe('לא מסווג')
  })
})
