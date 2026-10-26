import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { sampleRecipes } from '../test/sampleRecipes'
import CategoryChip from './CategoryChip'
import RecipeView from './RecipeView'

const [chocolateCake, chicken, , granola] = sampleRecipes

// compareDocumentPosition: is `later` after `earlier` in the page?
function comesAfter(earlier: Node, later: Node) {
  return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0
}

describe('RecipeView', () => {
  it('puts the ingredients above the preparation steps, each under its own heading', () => {
    render(<RecipeView recipe={chocolateCake} />)

    const firstIngredient = screen.getByText('200 גרם שוקולד מריר')
    const firstStep = screen.getByText('מחממים תנור ל-170 מעלות ומשמנים תבנית בקוטר 24.')
    expect(comesAfter(firstIngredient, firstStep)).toBe(true)
    expect(comesAfter(screen.getByRole('heading', { name: 'מצרכים' }), firstIngredient)).toBe(true)
    expect(comesAfter(screen.getByRole('heading', { name: 'אופן ההכנה' }), firstStep)).toBe(true)
    expect(comesAfter(firstIngredient, screen.getByRole('heading', { name: 'אופן ההכנה' }))).toBe(true)
  })

  it('keeps ingredient groups and the exact wording, including softened vs melted butter', () => {
    render(<RecipeView recipe={chocolateCake} />)

    expect(screen.getByRole('heading', { name: 'לעוגה' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'לגנאש' })).toBeInTheDocument()
    expect(screen.getByText('150 גרם חמאה מומסת')).toBeInTheDocument()
    expect(screen.getByText('30 גרם חמאה רכה')).toBeInTheDocument()
  })

  it('keeps alternative methods apart: each named group has its own list, numbered from 1', () => {
    render(<RecipeView recipe={chicken} />)

    for (const [name, step] of [
      ['בסיר לחץ', 'מבשלים 25 דקות מהרגע שהסיר מגיע ללחץ.'],
      ['בסיר רגיל', 'מבשלים על אש נמוכה כשעה וחצי, עד שהעוף רך.'],
    ]) {
      const heading = screen.getByRole('heading', { name })
      const list = screen.getByText(step).closest('ol')
      expect(heading.nextElementSibling).toBe(list) // the heading labels exactly this list
      expect(list).not.toHaveAttribute('start') // numbering restarts at 1
    }
  })

  it('marks ingredients that have no quantity instead of inventing one', () => {
    render(<RecipeView recipe={chicken} />)

    // A real space separates the words for screen readers and copy-paste, not only visually.
    expect(screen.getByText('מלח ופלפל').closest('li')).toHaveTextContent('מלח ופלפל ללא כמות')
    expect(screen.getByText('2 בצלים קצוצים').closest('li')).not.toHaveTextContent('ללא כמות')
    expect(screen.getAllByText('ללא כמות')).toHaveLength(2)
  })

  it('shows servings, the source and notes, and no notes section when there are none', () => {
    const { unmount } = render(<RecipeView recipe={chocolateCake} />)
    expect(screen.getByText('12 פרוסות')).toBeInTheDocument()
    expect(screen.getByText(/טקסט שהודבק/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'הערות' })).toBeInTheDocument()
    expect(screen.getByText('אפשר להחליף את השמנת המתוקה בחלב קוקוס.')).toBeInTheDocument()
    unmount()

    render(<RecipeView recipe={chicken} />)
    expect(screen.queryByRole('heading', { name: 'הערות' })).not.toBeInTheDocument()
  })

  it('shows a subcategory next to its category, and every creator', () => {
    // { ...recipe, key: value } copies an object and changes one property.
    const recipe = {
      ...chocolateCake,
      subcategory: { id: 5, name: 'עוגות' },
      sources: [{ kind: 'instagram' as const, url: null, creators: ['baker', 'partner.shop'] }],
    }
    render(<RecipeView recipe={recipe} />)

    expect(screen.getByText('קינוחים · עוגות')).toBeInTheDocument()
    expect(screen.getByText('baker').tagName).toBe('BDI')
    expect(screen.getByText('partner.shop').tagName).toBe('BDI')
  })

  it('says that a sample was invented, and says nothing of the kind for a saved recipe', () => {
    const { unmount } = render(<RecipeView recipe={chocolateCake} />)
    expect(screen.getByText(/מתכון דוגמה: הומצא/)).toBeInTheDocument()
    unmount()

    render(<RecipeView recipe={{ ...chocolateCake, is_sample: false }} />)
    expect(screen.queryByText(/מתכון דוגמה/)).not.toBeInTheDocument()
  })

  it('shows a typed-in source and when the recipe was last saved', () => {
    const recipe = {
      ...chicken,
      sources: [{ kind: 'manual' as const, url: null, creators: [] }],
      updated_at: '2026-10-20T09:30:00Z',
    }
    render(<RecipeView recipe={recipe} actions={<button type="button">עריכה</button>} />)

    expect(screen.getByText(/הוזן ידנית/)).toBeInTheDocument()
    // <time> keeps the exact moment for machines; the text shows it in the computer's time zone.
    expect(screen.getByText(/עודכן/).querySelector('time')).toHaveAttribute('dateTime', '2026-10-20T09:30:00Z')
    expect(screen.getByRole('button', { name: 'עריכה' })).toBeInTheDocument() // whatever App passes as actions
  })

  it('shows an unclassified English recipe with its text direction set from the content', () => {
    render(<RecipeView recipe={granola} />)

    expect(screen.getByText('לא מסווג')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2 })).toHaveAttribute('dir', 'auto')
    for (const text of ['2 cups rolled oats', 'Blend the dates with the tahini and honey into a thick paste.', 'Keeps for a week in the fridge.']) {
      expect(screen.getByText(text).closest('ul, ol')).toHaveAttribute('dir', 'auto')
    }
    expect(screen.getByText('12 bars')).toHaveAttribute('dir', 'auto')
    expect(screen.getByRole('link', { name: 'אתר' })).toHaveAttribute('href', 'https://example.com/granola-bars')
    expect(screen.getByText('Example Kitchen').tagName).toBe('BDI')
  })
})

describe('RecipeView for imported recipes', () => {
  const original = {
    kind: 'text' as const,
    text: 'עוף בסיר\n\nמטגנים את הבצל…',
    model: 'claude-opus-5-5',
    imported_at: '2026-10-20T09:30:00Z',
    url: null,
    retrieved_from: null,
  }

  it('marks a draft as not reviewed yet, with the number of points to check', () => {
    const issue = { kind: 'unclear_text' as const, message: 'לא ברור.', quote: null }
    render(<RecipeView recipe={{ ...chicken, status: 'draft', issues: [issue, issue], original }} />)
    expect(screen.getByText(/טיוטה מיובאת שעוד לא נבדקה \(2 נקודות לבדיקה\)/)).toBeInTheDocument()
  })

  it('keeps the original text, closed, below the facts', () => {
    render(<RecipeView recipe={{ ...chicken, original }} />)
    const details = screen.getByText('הטקסט המקורי').closest('details')!
    expect(details).not.toHaveAttribute('open')
    expect(details.querySelector('.original-text-body')?.textContent).toBe(original.text)
    expect(screen.getByText('claude-opus-5-5').tagName).toBe('BDI')
    expect(screen.queryByText(/טיוטה מיובאת/)).not.toBeInTheDocument()
  })
})

describe('the category chip', () => {
  it('shows a subcategory alone when its name starts with the category, and both otherwise', () => {
    const { rerender } = render(<CategoryChip category={{ id: 1, name: 'קינוחים' }} subcategory={{ id: 5, name: 'קינוחים רגילים' }} />)
    expect(screen.getByText('קינוחים רגילים')).toBeInTheDocument()
    rerender(<CategoryChip category={{ id: 3, name: 'ארוחות קלילות' }} subcategory={{ id: 7, name: 'פשטידות' }} />)
    expect(screen.getByText('ארוחות קלילות · פשטידות')).toBeInTheDocument()
    rerender(<CategoryChip category={null} />)
    expect(screen.getByText('לא מסווג')).toBeInTheDocument()
  })
})
