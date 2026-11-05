import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { fakeApi, type DraftMaker } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Issue, RecipeInput } from './types'

// Reviewing an imported draft's points about ingredients that only its steps name, against the fake backend: the
// line each point offers, adding it or ignoring the point, undoing either, and what a save keeps (or not).

const DECORATE = 'לקשט בתותים ולהנות מביס מושלם!'
const TEXTURE = 'מקציפים לקרם חלק במרקם של יוגורט.'
const STRAWBERRIES: Issue = {
  kind: 'ingredient_only_in_steps',
  message: 'המצרך "תותים" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
  quote: DECORATE,
  proposed: { text: 'תותים', quantity: null, group: null },
}
const YOGURT: Issue = {
  kind: 'ingredient_only_in_steps',
  message: 'המצרך "יוגורט" מופיע בהוראות ההכנה, אך חסר ברשימת המצרכים.',
  quote: TEXTURE,
  proposed: { text: 'יוגורט', quantity: null, group: null },
}

const torte: DraftMaker = () => ({
  title: 'טורט וניל',
  ingredient_groups: [
    { name: 'טורט וניל', ingredients: [{ text: '4 ביצים', quantity: '4' }] },
    { name: 'סירופ לעוגה', ingredients: [{ text: 'חצי כוס חלב', quantity: 'חצי כוס' }] },
  ],
  step_groups: [{ name: null, steps: [TEXTURE, DECORATE] }],
  issues: [STRAWBERRIES, YOGURT],
})

async function reviewDraft() {
  const user = userEvent.setup()
  const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories, draftFor: torte })
  render(<App />)
  await user.click(await screen.findByRole('button', { name: 'להדביק טקסט של מתכון' }))
  await screen.findByText(/נשלחים ל-Anthropic/)
  await user.click(screen.getByLabelText('טקסט המתכון'))
  await user.paste('טורט וניל\n4 ביצים')
  await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
  await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
  return { user, api }
}

const point = (message: string) => screen.getByText(message).closest('li')!
const ingredientTexts = () => screen.getAllByRole('textbox', { name: /^מצרך / }).map((input) => (input as HTMLInputElement).value)
const lastSave = (api: ReturnType<typeof fakeApi>) => api.changes().at(-1)!.body as RecipeInput

describe('a point about an ingredient only the steps name', () => {
  it('shows the line it would add, and adds only on its button, labeled, with the decision recorded', async () => {
    const { user, api } = await reviewDraft()
    const strawberries = point(STRAWBERRIES.message)
    expect(within(strawberries).getByText(DECORATE)).toBeInTheDocument()
    expect(strawberries).toHaveTextContent('השורה שתתווסף: תותים · ללא כמות · בלי קבוצה')

    await user.click(within(strawberries).getByText(DECORATE)) // the sentence and the point itself add nothing
    await user.click(within(strawberries).getByText(STRAWBERRIES.message))
    expect(ingredientTexts()).toEqual(['4 ביצים', 'חצי כוס חלב'])

    await user.click(screen.getByRole('button', { name: 'הוספת תותים למצרכים' }))
    expect(ingredientTexts()).toEqual(['4 ביצים', 'חצי כוס חלב', 'תותים'])
    expect(screen.getByLabelText('כמות במצרך 1 בקבוצה 3')).toHaveValue('') // no amount
    expect(screen.getByLabelText('מצרך 1 בקבוצה 3')).toHaveAccessibleDescription(`נוסף מהוראות ההכנה ${DECORATE}`)
    expect(screen.queryByRole('button', { name: 'הוספת תותים למצרכים' })).not.toBeInTheDocument() // no second click
    const decided = screen.getByRole('heading', { name: 'הוחלט בבדיקה (1)' }).parentElement!
    expect(decided).toHaveTextContent('נוסף למצרכים')
    expect(decided).toHaveTextContent('לא נשמר עדיין')
    // Still editable, movable and removable like any line.
    await user.type(screen.getByLabelText('מצרך 1 בקבוצה 3'), ' לקישוט')
    expect(screen.getByRole('button', { name: 'הסרת מצרך 1 בקבוצה 3' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'הזזת קבוצת מצרכים 3 למעלה' })).toBeEnabled()

    // The yogurt is a texture: ignored, nothing added. The untouched draft is then saved as a draft.
    await user.click(screen.getByRole('button', { name: `התעלמות: ${YOGURT.message}` }))
    expect(ingredientTexts()).toEqual(['4 ביצים', 'חצי כוס חלב', 'תותים לקישוט'])
    await user.click(screen.getByRole('button', { name: 'שמירת טיוטה' }))
    await screen.findByText(/הטיוטה נשמרה/)
    const saved = lastSave(api)
    expect(saved.issues).toEqual([])
    expect(saved.resolved_issues).toEqual([
      { ...STRAWBERRIES, resolution: 'added' },
      { ...YOGURT, resolution: 'dismissed' },
    ])
    expect(saved.ingredient_groups[2]).toEqual({
      name: null,
      ingredients: [{ text: 'תותים לקישוט', quantity: null, derived_from: DECORATE, added_in_review: true }],
    })

    // Opened again: both decisions are kept, saved; the dismissed point stays dismissed until undone.
    await user.click(screen.getByRole('button', { name: 'בדיקה ושמירה' }))
    expect(screen.getByText('אין נקודות פתוחות לבדיקה.')).toBeInTheDocument()
    expect(screen.queryByText('לא נשמר עדיין')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: `ביטול: ${YOGURT.message}` }))
    expect(screen.getByRole('heading', { name: 'לבדיקה (1)' })).toBeInTheDocument()
    expect(point(YOGURT.message)).toBeInTheDocument()
  })

  it('offers no addition for an ingredient already typed into the list, only marking the point done', async () => {
    const { user } = await reviewDraft()
    await user.click(screen.getByRole('button', { name: 'הוספת מצרך לקבוצה 2' }))
    await user.type(screen.getByLabelText('מצרך 2 בקבוצה 2'), 'תותים')
    const strawberries = point(STRAWBERRIES.message)
    expect(strawberries).toHaveTextContent('כבר יש ברשימת המצרכים שורה עם "תותים".')
    expect(screen.queryByRole('button', { name: 'הוספת תותים למצרכים' })).not.toBeInTheDocument()
    await user.click(within(strawberries).getByRole('button', { name: `טופל: ${STRAWBERRIES.message}` }))
    expect(ingredientTexts().filter((text) => text === 'תותים')).toHaveLength(1)
  })

  it('undoing an addition before saving takes its line out and opens the point again', async () => {
    const { user } = await reviewDraft()
    await user.click(screen.getByRole('button', { name: 'הוספת תותים למצרכים' }))
    await user.click(screen.getByRole('button', { name: 'ביטול: תותים' }))
    expect(ingredientTexts()).toEqual(['4 ביצים', 'חצי כוס חלב'])
    expect(screen.getByRole('button', { name: 'הוספת תותים למצרכים' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /הוחלט בבדיקה/ })).not.toBeInTheDocument()
  })

  it('after a failed save, the notebook still has the point open and the page says the decision is not saved', async () => {
    const { user, api } = await reviewDraft()
    await user.click(screen.getByRole('button', { name: 'הוספת תותים למצרכים' }))
    api.answerNextWith(500, { error: { code: 'internal_error', message: 'Something went wrong.', details: null } })
    await user.click(screen.getByRole('button', { name: 'שמירת טיוטה' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('לא נשמר עדיין')).toBeInTheDocument()
    const stored = api.recipes().find((recipe) => recipe.title === 'טורט וניל')!
    expect(stored.issues).toEqual([STRAWBERRIES, YOGURT])
    expect(stored.resolved_issues).toEqual([])
    expect(stored.ingredient_groups.flatMap((group) => group.ingredients).map((item) => item.text)).not.toContain('תותים')
  })
})
