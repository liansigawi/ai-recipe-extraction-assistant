import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Category, Recipe } from './types'

// "Already cooked", against the fake backend. The cake is marked; the others are not. Desserts have two
// subcategories (the cake in "קינוחים רגילים"), and a dessert draft has none.
const categories: Category[] = [
  {
    ...sampleCategories[0],
    subcategories: [
      { id: 10, name: 'קינוחים רגילים', description: null },
      { id: 11, name: 'קינוחים בריאים', description: null },
    ],
  },
  ...sampleCategories.slice(1),
]
const [cake, chicken, pizza, granola] = sampleRecipes
const draft: Recipe = { ...cake, id: 9, title: 'כדורי תמרים', status: 'draft', subcategory: null, is_sample: false }
const recipes: Recipe[] = [draft, { ...cake, cooked: true, subcategory: { id: 10, name: 'קינוחים רגילים' } }, chicken, pizza, granola]

async function renderApp(list: Recipe[] = recipes) {
  const user = userEvent.setup()
  const api = fakeApi({ recipes: list, categories })
  render(<App />)
  await screen.findByRole('region', { name: 'המתכונים' })
  return { user, api }
}

const gallery = () => within(screen.getByRole('region', { name: 'המתכונים' }))
const card = (title: string) => gallery().getByRole('button', { name: new RegExp(title) })
// The card's badge: a toggle button of its own, beside the card's button.
const badge = (title: string) => within(card(title).closest('li')!).getByRole('button', { name: 'כבר הכנתי' })
const cardTitles = () => gallery().queryAllByRole('listitem').map((item) => item.querySelector('.recipe-card-title')?.textContent)
const group = (name: string) => within(screen.getByRole('group', { name }))
const cookedChoice = (name: RegExp) => group('מה כבר הכנתי').getByRole('radio', { name })
const toggle = () => screen.getByRole('checkbox', { name: 'כבר הכנתי' })

describe('already cooked', () => {
  it('every card says whether it was cooked, in text and not only color', async () => {
    await renderApp()
    expect(badge(cake.title)).toHaveTextContent('כבר הכנתי')
    expect(badge(cake.title)).toHaveAttribute('aria-pressed', 'true')
    expect(badge(cake.title).querySelector('.icon-check')).not.toBeNull() // and an icon
    for (const recipe of [draft, chicken, pizza, granola]) {
      expect(badge(recipe.title)).toHaveTextContent('טרם הכנתי')
      expect(badge(recipe.title)).toHaveAttribute('aria-pressed', 'false')
    }
  })

  it('the control beside the title saves at once, shows on the card, and the change can be undone', async () => {
    const { user, api } = await renderApp()
    await user.click(card(pizza.title))
    expect(toggle()).not.toBeChecked()

    await user.click(toggle())
    expect(api.changes()).toEqual([{ method: 'PUT', path: `/api/recipes/${pizza.id}/cooked`, body: { cooked: true } }])
    expect(await screen.findByText('סומן: כבר הכנתי.')).toBeInTheDocument()
    expect(toggle()).toBeChecked()

    await user.click(screen.getByRole('button', { name: 'ביטול' }))
    expect(api.changes().at(-1)).toEqual({ method: 'PUT', path: `/api/recipes/${pizza.id}/cooked`, body: { cooked: false } })
    expect(toggle()).not.toBeChecked()
    expect(screen.queryByRole('button', { name: 'ביטול' })).not.toBeInTheDocument() // an undo is not undone again

    await user.click(toggle())
    await screen.findByText('סומן: כבר הכנתי.')
    await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
    expect(badge(pizza.title)).toHaveTextContent('כבר הכנתי')
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 2')
  })

  it('unmarking a recipe works the same way', async () => {
    const { user, api } = await renderApp()
    await user.click(card(cake.title))
    expect(toggle()).toBeChecked()
    await user.click(toggle())
    expect(await screen.findByText('הסימון הוסר.')).toBeInTheDocument()
    expect(api.changes()).toEqual([{ method: 'PUT', path: `/api/recipes/${cake.id}/cooked`, body: { cooked: false } }])
  })

  it('the three filters show how many recipes each would show', async () => {
    await renderApp()
    expect(cookedChoice(/^הכול/)).toHaveAccessibleName('הכול 5')
    expect(cookedChoice(/טרם הכנתי/)).toHaveAccessibleName('טרם הכנתי 4')
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 1')
    expect(cookedChoice(/^הכול/)).toBeChecked()
  })

  it('combine with the search, the category, the subcategory and drafts; the counts follow', async () => {
    const { user } = await renderApp()
    await user.click(cookedChoice(/טרם הכנתי/))
    expect(cardTitles()).toEqual([draft.title, chicken.title, pizza.title, granola.title])

    await user.click(group('קטגוריה').getByRole('radio', { name: 'קינוחים' }))
    expect(cardTitles()).toEqual([draft.title]) // the dessert not cooked yet
    expect(cookedChoice(/^הכול/)).toHaveAccessibleName('הכול 2')
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 1')

    await user.click(cookedChoice(/כבר הכנתי/))
    await user.click(group('קינוחים:').getByRole('radio', { name: 'קינוחים רגילים' }))
    expect(cardTitles()).toEqual([cake.title])
    await user.click(group('מתכונים וטיוטות').getByRole('radio', { name: 'טיוטות' }))
    expect(screen.getByText('לא נמצאו מתכונים שמתאימים לחיפוש ולסינון.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'ניקוי החיפוש והסינון' }))
    await user.type(screen.getByRole('searchbox', { name: 'חיפוש לפי שם מתכון או מצרך' }), 'שוקולד')
    await user.click(cookedChoice(/כבר הכנתי/))
    expect(cardTitles()).toEqual([cake.title])
    expect(screen.getByText('1 מתוך 5 מתכונים')).toBeInTheDocument()
  })

  it('a mark that could not be saved says why, and stays as it was', async () => {
    const { user, api } = await renderApp()
    await user.click(card(pizza.title))
    api.answerNextWith(500, { error: { code: 'internal_error', message: 'Something went wrong on the server.', details: null } })
    await user.click(toggle())
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong on the server.')
    expect(toggle()).not.toBeChecked()
    expect(api.recipes().find((recipe) => recipe.id === pizza.id)?.cooked).toBe(false)
  })

  it("the card's badge changes the mark in both directions without opening the recipe", async () => {
    const { user, api } = await renderApp()
    await user.click(badge(pizza.title))
    expect(api.changes()).toEqual([{ method: 'PUT', path: `/api/recipes/${pizza.id}/cooked`, body: { cooked: true } }])
    expect(badge(pizza.title)).toHaveAttribute('aria-pressed', 'true')
    expect(badge(pizza.title)).toHaveTextContent('כבר הכנתי')
    expect(screen.queryByRole('article')).not.toBeInTheDocument() // still the gallery
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 2') // the counts follow

    await user.click(badge(pizza.title))
    expect(api.changes().at(-1)?.body).toEqual({ cooked: false })
    expect(badge(pizza.title)).toHaveAttribute('aria-pressed', 'false')
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 1')

    await user.click(card(pizza.title)) // the rest of the card still opens the recipe
    expect(screen.getByRole('heading', { level: 2, name: pizza.title })).toBeInTheDocument()
  })

  it('works with the keyboard: Enter and Space on the badge, which keeps the focus', async () => {
    const { user, api } = await renderApp()
    badge(chicken.title).focus()
    await user.keyboard('{Enter}')
    expect(badge(chicken.title)).toHaveAttribute('aria-pressed', 'true')
    expect(badge(chicken.title)).toHaveFocus()
    await user.keyboard(' ')
    expect(badge(chicken.title)).toHaveAttribute('aria-pressed', 'false')
    expect(api.changes()).toHaveLength(2)
  })

  it('sends one change while it is being saved, however often it is pressed', async () => {
    const { user, api } = await renderApp()
    const release = api.holdNext()
    await user.click(badge(pizza.title))
    expect(badge(pizza.title)).toHaveAttribute('aria-disabled', 'true')
    await user.click(badge(pizza.title))
    await user.click(badge(pizza.title))
    expect(badge(pizza.title)).toHaveAttribute('aria-pressed', 'false') // not shown as saved before it is
    release()
    await screen.findByRole('button', { name: 'כבר הכנתי', pressed: true, description: pizza.title })
    expect(api.changes()).toEqual([{ method: 'PUT', path: `/api/recipes/${pizza.id}/cooked`, body: { cooked: true } }])
    expect(badge(pizza.title)).not.toHaveAttribute('aria-disabled')
  })

  it('a badge whose change could not be saved says why, and shows the saved mark', async () => {
    const { user, api } = await renderApp()
    api.answerNextWith(500, { error: { code: 'internal_error', message: 'Something went wrong on the server.', details: null } })
    await user.click(badge(pizza.title))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(`הסימון של ${pizza.title} לא נשמר`)
    expect(alert).toHaveTextContent('Something went wrong on the server.')
    expect(badge(pizza.title)).toHaveAttribute('aria-pressed', 'false')
    expect(cookedChoice(/כבר הכנתי/)).toHaveAccessibleName('כבר הכנתי 1')
    await user.click(within(alert).getByRole('button', { name: 'סגירת ההודעה' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('under a filter, a card that no longer matches leaves with a note that can undo it', async () => {
    const { user, api } = await renderApp()
    await user.click(cookedChoice(/טרם הכנתי/))
    await user.click(badge(pizza.title))

    expect(cardTitles()).toEqual([draft.title, chicken.title, granola.title])
    const note = screen.getByText(/הסינון הנוכחי לא מציג אותו/)
    expect(note).toHaveTextContent(`סומן "כבר הכנתי": ${pizza.title}`)
    const undo = screen.getByRole('button', { name: 'ביטול' })
    expect(undo).toHaveFocus() // the badge that had the focus left with its card
    expect(cookedChoice(/טרם הכנתי/)).toHaveAccessibleName('טרם הכנתי 3')

    await user.click(undo)
    expect(api.changes().at(-1)).toEqual({ method: 'PUT', path: `/api/recipes/${pizza.id}/cooked`, body: { cooked: false } })
    expect(cardTitles()).toEqual([draft.title, chicken.title, pizza.title, granola.title])
    expect(badge(pizza.title)).toHaveFocus()
    expect(screen.queryByText(/הסינון הנוכחי לא מציג אותו/)).not.toBeInTheDocument()

    // Under the filter, the card itself still opens the recipe.
    await user.click(card(chicken.title))
    expect(screen.getByRole('heading', { level: 2, name: chicken.title })).toBeInTheDocument()
  })

  it('marks come from the notebook, so they are there after a reload', async () => {
    const { user } = await renderApp([{ ...chicken, cooked: true }, pizza])
    expect(badge(chicken.title)).toHaveTextContent('כבר הכנתי')
    await user.click(card(chicken.title))
    expect(toggle()).toBeChecked()
    expect(screen.getByText('מסומן · לחיצה מבטלת')).toBeInTheDocument()
  })
})
