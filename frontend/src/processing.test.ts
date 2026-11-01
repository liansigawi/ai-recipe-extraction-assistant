import { describe, expect, it } from 'vitest'
import { diffLines, elapsedText, reviewChanges } from './processing'
import type { KeptDraft, Recipe } from './types'

describe('the lines that differ', () => {
  it('a changed line is one removal and one addition; the lines around it are left out', () => {
    expect(diffLines(['a', 'b', 'c'], ['a', 'B', 'c'])).toEqual([
      { kind: 'removed', text: 'b' },
      { kind: 'added', text: 'B' },
    ])
  })

  it('a line added or removed does not mark the lines after it', () => {
    expect(diffLines(['a', 'c'], ['a', 'b', 'c'])).toEqual([{ kind: 'added', text: 'b' }])
    expect(diffLines(['a', 'b', 'c'], ['a', 'c'])).toEqual([{ kind: 'removed', text: 'b' }])
    expect(diffLines(['a'], ['a'])).toEqual([])
  })
})

const draft: KeptDraft = {
  title: 'שייק בננה',
  servings: null,
  category: null,
  subcategory: null,
  ingredient_groups: [{ name: null, ingredients: [{ text: 'חצי תמר מג׳ hollow', quantity: 'חצי' }, { text: 'כוס חלב', quantity: 'כוס' }] }],
  step_groups: [{ name: null, steps: ['מערבלים.'] }],
  notes: [],
  issues: [],
  saved_at: '2026-10-20T10:52:14Z',
}

function saved(fields: Partial<Recipe>): Recipe {
  return {
    ...draft,
    sources: [],
    id: 6,
    is_sample: false,
    status: 'saved',
    issues: [],
    cooked: true,
    original: null,
    media: [],
    cover_id: null,
    created_at: draft.saved_at,
    updated_at: '2026-10-26T14:21:42Z',
    ...fields,
  }
}

describe('what review changed', () => {
  it('only a category chosen: one part changed, the others named as unchanged', () => {
    const { changed, unchanged } = reviewChanges(draft, saved({ category: { id: 4, name: 'משקאות' } }))
    expect(changed).toEqual([
      {
        part: 'קטגוריה',
        lines: [
          { kind: 'removed', text: 'לא מסווג' },
          { kind: 'added', text: 'משקאות' },
        ],
      },
    ])
    expect(unchanged).toEqual(['כותרת', 'כמות מנות', 'מצרכים', 'אופן ההכנה', 'הערות'])
  })

  it('a corrected ingredient line shows as it was and as saved, with its quantity', () => {
    const fixed = saved({ ingredient_groups: [{ name: null, ingredients: [{ text: 'חצי תמר מג׳הול', quantity: 'חצי' }, { text: 'כוס חלב', quantity: 'כוס' }] }] })
    expect(reviewChanges(draft, fixed).changed).toEqual([
      {
        part: 'מצרכים',
        lines: [
          { kind: 'removed', text: 'חצי תמר מג׳ hollow · כמות: חצי' },
          { kind: 'added', text: 'חצי תמר מג׳הול · כמות: חצי' },
        ],
      },
    ])
  })

  it('a quantity changed alone shows too', () => {
    const fixed = saved({ ingredient_groups: [{ name: null, ingredients: [{ text: 'חצי תמר מג׳ hollow', quantity: null }, { text: 'כוס חלב', quantity: 'כוס' }] }] })
    expect(reviewChanges(draft, fixed).changed[0].lines).toEqual([
      { kind: 'removed', text: 'חצי תמר מג׳ hollow · כמות: חצי' },
      { kind: 'added', text: 'חצי תמר מג׳ hollow · ללא כמות' },
    ])
  })
})

describe('time between two moments', () => {
  it.each([
    ['2026-10-28T13:35:22Z', 'פחות מדקה'],
    ['2026-10-28T13:36:03Z', 'דקה'],
    ['2026-10-28T13:39:10Z', '4 דקות'],
    ['2026-10-28T15:40:00Z', 'שעתיים'],
    ['2026-11-03T13:35:00Z', '6 ימים'],
  ])('until %s: %s', (to, text) => {
    expect(elapsedText('2026-10-28T13:35:00Z', to)).toBe(text)
  })
})
