import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Category, Recipe } from './types'

// Searching and filtering the list, against the fake backend: desserts have two subcategories, the
// cake is in "קינוחים רגילים", and a dessert draft has no subcategory.
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
const [cake, ...others] = sampleRecipes
const draft: Recipe = {
  ...cake,
  id: 9,
  title: 'כדורי תמרים',
  status: 'draft',
  subcategory: null,
  ingredient_groups: [{ name: null, ingredients: [{ text: 'כוס תמרים', quantity: 'כוס' }] }],
}
const recipes: Recipe[] = [draft, { ...cake, subcategory: { id: 10, name: 'קינוחים רגילים' } }, ...others]

async function renderApp() {
  const user = userEvent.setup()
  fakeApi({ recipes, categories })
  render(<App />)
  await screen.findByRole('heading', { level: 2, name: 'כדורי תמרים' })
  return user
}

const cardTitles = () =>
  within(screen.getByRole('navigation'))
    .queryAllByRole('listitem')
    .map((item) => item.querySelector('.recipe-card-title, h3')?.textContent ?? item.textContent)
const searchBox = () => screen.getByRole('searchbox', { name: 'חיפוש לפי שם מתכון או מצרך' })
const categoryFilter = () => screen.getByLabelText('סינון לפי קטגוריה')

describe('searching and filtering the recipe list', () => {
  it('searches titles and ingredient lines, says how many match, and clears', async () => {
    const user = await renderApp()
    expect(screen.getByText('5 מתכונים')).toBeInTheDocument()
    await user.type(searchBox(), 'כורכום')
    expect(cardTitles()).toHaveLength(1)
    expect(within(screen.getByRole('navigation')).getByText(/עוף בסיר עם אורז/)).toBeInTheDocument()
    expect(screen.getByText('1 מתוך 5 מתכונים')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'ניקוי' }))
    expect(searchBox()).toHaveValue('')
    expect(cardTitles()).toHaveLength(5)
  })

  it('a top-level category shows all its recipes; a subcategory narrows them', async () => {
    const user = await renderApp()
    await user.selectOptions(categoryFilter(), 'קינוחים')
    expect(cardTitles()).toHaveLength(2) // the cake (in a subcategory) and the draft (in none)
    await user.selectOptions(categoryFilter(), 's:10') // "↳ קינוחים רגילים", indented under its category
    expect(cardTitles()).toHaveLength(1)
    expect(within(screen.getByRole('navigation')).getByText(/עוגת שוקולד עם גנאש/)).toBeInTheDocument()
  })

  it('finds unclassified recipes, and shows drafts only or saved recipes only', async () => {
    const user = await renderApp()
    await user.selectOptions(categoryFilter(), 'לא מסווג')
    expect(cardTitles()).toHaveLength(1)
    expect(within(screen.getByRole('navigation')).getByText(/Oat and Date Granola Bars/)).toBeInTheDocument()
    await user.selectOptions(categoryFilter(), 'כל הקטגוריות')
    await user.click(screen.getByRole('radio', { name: 'טיוטות' }))
    expect(cardTitles()).toHaveLength(1)
    await user.click(screen.getByRole('radio', { name: 'מתכונים' }))
    expect(cardTitles()).toHaveLength(4)
  })

  it('combines a search with filters, and says clearly when nothing matches', async () => {
    const user = await renderApp()
    await user.selectOptions(categoryFilter(), 'קינוחים')
    await user.click(screen.getByRole('radio', { name: 'מתכונים' }))
    await user.type(searchBox(), 'תמרים') // only the draft has dates: nothing saved matches
    expect(screen.getByText('לא נמצאו מתכונים שמתאימים לחיפוש ולסינון.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'ניקוי החיפוש והסינון' }))
    expect(cardTitles()).toHaveLength(5)
    expect(categoryFilter()).toHaveValue('all')
    expect(screen.getByRole('radio', { name: 'הכל' })).toBeChecked()
  })
})
