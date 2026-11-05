import { describe, expect, it } from 'vitest'
import { demonstrationSummary, diffLines, elapsedText, reviewChanges } from './processing'
import type { Category, Demonstration, Issue, KeptDraft, Recipe } from './types'

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
    healthy: null,
    sources: [],
    id: 6,
    is_sample: false,
    status: 'saved',
    issues: [],
    resolved_issues: [],
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

  it("a dessert's healthy style is part of its category: the same choice is no change, another one is", () => {
    const desserts = { id: 1, name: 'קינוחים' }
    const regular = { ...draft, category: desserts, healthy: false }
    expect(reviewChanges(regular, saved({ category: desserts, healthy: false })).unchanged).toContain('קטגוריה')
    expect(reviewChanges(regular, saved({ category: desserts, healthy: true })).changed).toEqual([
      {
        part: 'קטגוריה',
        lines: [
          { kind: 'removed', text: 'קינוחים · לא קינוח בריא' },
          { kind: 'added', text: 'קינוחים · קינוח בריא' },
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

describe('what happened in a demonstration, from its record only', () => {
  const chocolate: Issue = {
    kind: 'ingredient_only_in_steps',
    message: 'המצרך "שוקולד" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
    quote: 'ממיסים 200 גרם שוקולד.',
    proposed: { text: '200 גרם שוקולד', quantity: '200 גרם', group: null },
  }
  const yogurt: Issue = { ...chocolate, message: 'המצרך "יוגורט" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.', proposed: { text: 'יוגורט', quantity: null, group: null } }
  const categories: Category[] = [
    { id: 1, name: 'קינוחים', description: null, subcategories: [], healthy_style: true },
    { id: 3, name: 'ארוחות קלילות', description: null, subcategories: [] },
  ]
  const record = (reviewed: Partial<Demonstration['reviewed']>): Demonstration => ({
    run_at: '2026-11-05T08:31:24Z',
    model: 'qwen3:8b',
    draft: { ...draft, category: { id: 3, name: 'ארוחות קלילות' }, healthy: null, issues: [chocolate, yogurt] },
    reviewed: { ...draft, category: { id: 3, name: 'ארוחות קלילות' }, healthy: null, issues: [], resolved_issues: [], ...reviewed },
  })

  it('says what was added with its own amount, what was dismissed, and credits the model only with its choices', () => {
    const added = { ...draft.ingredient_groups[0], ingredients: [...draft.ingredient_groups[0].ingredients] }
    const { items, unchanged } = demonstrationSummary(
      record({
        category: { id: 1, name: 'קינוחים' },
        ingredient_groups: [added, { name: null, ingredients: [{ text: '200 גרם שוקולד', quantity: '200 גרם', derived_from: chocolate.quote, added_in_review: true }] }],
        resolved_issues: [{ ...chocolate, resolution: 'added' }, { ...yogurt, resolution: 'dismissed' }],
        title: 'שייק בננה ותמר',
      }),
      categories,
    )
    expect(items.map((item) => [item.topic, item.tags])).toEqual([
      ['שוקולד', ['detected', 'approved']],
      ['יוגורט', ['detected', 'dismissed']],
      ['קטגוריה', ['model', 'corrected']],
      ['תיקונים נוספים', ['corrected']],
    ])
    expect(items[0].text).toContain('ו"200 גרם שוקולד" נוסף למצרכים עם הכמות שכתובה בהוראות, "200 גרם".')
    expect(items[1].text).toContain('בבדיקה הוחלט להתעלם מההתרעה, ולא נוסף דבר.')
    expect(items[2].text).toBe('המודל הציע "ארוחות קלילות"; בבדיקה זה תוקן ל"קינוחים".')
    expect(items[3].text).toBe('בבדיקה תוקנו גם: כותרת. הפירוט בטיוטה שלפני הבדיקה.') // the added line is the decision, not another correction
    expect(unchanged).toEqual(['כמות מנות', 'אופן ההכנה', 'הערות'])
  })

  it('names nothing review did not record', () => {
    const { items, unchanged } = demonstrationSummary(record({}), categories)
    expect(items).toEqual([])
    expect(unchanged).toEqual(['כותרת', 'כמות מנות', 'קטגוריה', 'מצרכים', 'אופן ההכנה', 'הערות'])
  })
})
