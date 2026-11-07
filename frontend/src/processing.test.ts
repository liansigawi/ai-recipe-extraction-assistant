import { describe, expect, it } from 'vitest'
import { demonstrationAccount, diffLines, elapsedText, pointOrigin, reviewChanges } from './processing'
import type { Demonstration, Issue, KeptDraft, Recipe } from './types'

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

describe('who did what in a demonstration, from its record only', () => {
  const strawberries: Issue = {
    kind: 'ingredient_only_in_steps',
    message: 'המצרך "תותים" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
    quote: 'לקשט בתותים.',
    proposed: { text: 'תותים', quantity: null, group: null },
  }
  const unclearOr: Issue = { kind: 'ambiguous_alternative', message: 'בקטע הזה יש "או" שלא ברור על מה הוא חל.', quote: 'חמאה או שמן' }
  const reference = 'מכינים בצק לפי המתכון שלי מהבלוג.'
  const record = (fields: Partial<Demonstration>): Demonstration => ({
    run_at: '2026-11-07T11:51:28Z',
    model: 'qwen3:8b',
    draft: { ...draft, title: 'עוגה', category: { id: 1, name: 'קינוחים' }, subcategory: { id: 13, name: 'טארטים ופאי' }, healthy: null },
    reviewed: { ...draft, title: 'עוגה', healthy: null, issues: [], resolved_issues: [] },
    ...fields,
  })

  it("credits the model with its labels, its title and its category, and the rules with what they did on their own", () => {
    const demo = record({
      answer: {
        classification: { fit: 'clear', category_id: 1, subcategory_id: 13, candidate_category_ids: [] },
        points: [
          { kind: 'ambiguous_alternative', passage: 'טורפים את החלמונים.', left_out: 'no_alternative' },
          { kind: 'ambiguous_alternative', passage: 'מקציפים את הקרם.', left_out: 'no_alternative' },
        ],
      },
      automatic: [
        { kind: 'joined_remark', step: 'אופים 50 דקות', remark: '(כל תנור עובד אחרת).' },
        { kind: 'kept_reference', text: reference, kept_as: 'step' },
      ],
      draft: {
        ...record({}).draft,
        step_groups: [{ name: null, steps: ['מערבלים.', reference] }],
        issues: [strawberries],
      },
    })
    const { model, rules } = demonstrationAccount(demo)
    // The reference step is the rule's, not the model's: one step copied by the labels.
    expect(model[0]).toBe('סימן לכל קטע בטקסט את תפקידו: כותרת, מצרך, שלב, הערה, או לא חלק מהמתכון. לפי הסימון הועתקו מהטקסט, מילה במילה, 2 שורות מצרכים ושלב אחד.')
    expect(model.slice(1)).toEqual(['סימן את שורת הכותרת: "עוגה".', 'בחר בקטגוריה "קינוחים · טארטים ופאי".', 'סימן 2 נקודות לבדיקה; אף אחת מהן לא הוצגה.'])
    expect(rules).toEqual([
      'קראה את הכמות בכל שורת מצרך מתוך השורה עצמה, לפי כללים קבועים: היא מסומנת בתוצאה.',
      'צירפה את ההערה "(כל תנור עובד אחרת)." לשלב שלפניה: במקור היא חותמת את המשפט שלו, בשורה הבאה.',
      `שמרה כשלב, מילה במילה, את הקטע "${reference}", אף שהמודל סימן אותו כלא חלק מהמתכון: הקטע מפנה למתכון נפרד, שלא כלול בטקסט ולא יובא.`,
      'לא הציגה 2 נקודות של המודל על "או" לא ברור: בקטעים שהמודל הצביע עליהם אין "או".',
      'סימנה נקודה אחת לבדיקה, בבדיקות שלה (בפירוט למטה).',
    ])
  })

  it('a composed title and an unclear category are the model\'s too', () => {
    const titlePoint: Issue = { kind: 'missing_title', message: 'אין בטקסט שורת כותרת.', quote: 'איזה שם מתאים יותר?' }
    const { model } = demonstrationAccount(record({ draft: { ...record({}).draft, category: null, subcategory: null, issues: [titlePoint] } }))
    expect(model.slice(1)).toEqual(['בטקסט אין שורת כותרת, והמודל בחר בכותרת "עוגה".', 'לא בחר קטגוריה אחת בבירור.'])
  })

  it("a point is the model's only when its answer raised it and the import showed it; the others are the system's", () => {
    const answer = {
      classification: { fit: 'clear' as const, category_id: 1, subcategory_id: 13, candidate_category_ids: [] },
      points: [{ kind: 'ambiguous_alternative' as const, passage: 'חמאה או שמן', left_out: null }],
    }
    expect(pointOrigin(unclearOr, record({ answer }))).toBe('model')
    expect(pointOrigin(strawberries, record({ answer }))).toBe('system')
    expect(pointOrigin(strawberries, record({}))).toBeNull() // an older record does not say
  })
})
