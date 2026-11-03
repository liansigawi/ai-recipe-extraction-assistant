import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Category } from './types'

// A dessert's type (its subcategory) and, separately, whether it is in the healthy style: in the editor,
// on the recipe and in the categories screen, against the fake backend (which refuses the style on a
// recipe that is not a dessert, as the real one does).
const TYPES = ['עוגות', 'עוגיות וחיתוכיות', 'טארטים ופאי', 'קינוחי כוסות ומוסים', 'גלידות וקינוחים קפואים', 'מאפים מתוקים']
const categories: Category[] = [
  { ...sampleCategories[0], healthy_style: true, subcategories: TYPES.map((name, index) => ({ id: 11 + index, name, description: null })) },
  ...sampleCategories.slice(1),
]

async function openEditor(title: RegExp) {
  const user = userEvent.setup()
  const api = fakeApi({ recipes: sampleRecipes, categories })
  render(<App />)
  await user.click(await screen.findByRole('button', { name: title }))
  await user.click(screen.getByRole('button', { name: 'עריכה' }))
  return { user, api }
}

const healthy = () => screen.queryByRole('group', { name: 'קינוח בריא' })

describe('dessert types and the healthy style', () => {
  it('a dessert gets a type and, apart from it, the healthy style; both are saved and shown', async () => {
    const { user, api } = await openEditor(/עוגת שוקולד עם גנאש/)
    expect(within(healthy()!).getByRole('radio', { name: 'לא נקבע' })).toBeChecked() // undecided until someone decides
    await user.selectOptions(screen.getByLabelText('תת-קטגוריה'), 'גלידות וקינוחים קפואים')
    await user.click(within(healthy()!).getByRole('radio', { name: 'כן' }))
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    const [save] = api.changes()
    expect(save.body).toMatchObject({ category_id: 1, subcategory_id: 15, healthy: true })
    // The saved recipe: its category with the type, and the healthy style beside it.
    expect(await screen.findByText('קינוחים · גלידות וקינוחים קפואים', { selector: '.chip' })).toBeInTheDocument()
    expect(screen.getByText('קינוח בריא', { selector: '.chip-healthy' })).toBeInTheDocument()
  })

  it('the healthy style is offered only for desserts and goes when the category changes', async () => {
    const { user, api } = await openEditor(/עוגת שוקולד עם גנאש/)
    await user.click(within(healthy()!).getByRole('radio', { name: 'לא' }))
    await user.selectOptions(screen.getByLabelText('קטגוריה'), 'ארוחות קלילות')
    expect(healthy()).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(api.changes()[0].body).toMatchObject({ category_id: 3, subcategory_id: null, healthy: null })
  })

  it('the categories screen says that desserts have the healthy style beside their types', async () => {
    const user = userEvent.setup()
    fakeApi({ recipes: sampleRecipes, categories })
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'קטגוריות' }))
    const desserts = (await screen.findByRole('heading', { level: 3, name: 'קינוחים' })).closest('li')!
    expect(desserts).toHaveTextContent('קינוח בריא: סימון נפרד מהסוג')
    expect(within(screen.getByRole('list', { name: 'תת-קטגוריות של קינוחים' })).getAllByRole('heading', { level: 4 }).map((h) => h.textContent)).toEqual(TYPES)
    const meals = screen.getByRole('heading', { level: 3, name: 'ארוחות קלילות' }).closest('li')!
    expect(meals).not.toHaveTextContent('קינוח בריא')
  })
})
