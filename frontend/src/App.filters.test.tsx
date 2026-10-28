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
  await screen.findByRole('region', { name: 'המתכונים' })
  return user
}

const gallery = () => within(screen.getByRole('region', { name: 'המתכונים' }))
const cardTitles = () =>
  gallery()
    .queryAllByRole('listitem')
    .map((item) => item.querySelector('.recipe-card-title')?.textContent)
const searchBox = () => screen.getByRole('searchbox', { name: 'חיפוש לפי שם מתכון או מצרך' })
const group = (name: string) => within(screen.getByRole('group', { name }))
const pick = (user: ReturnType<typeof userEvent.setup>, groupName: string, choice: string | RegExp) =>
  user.click(group(groupName).getByRole('radio', { name: choice }))

describe('searching and filtering the recipe gallery', () => {
  it('searches titles and ingredient lines, says how many match, and clears', async () => {
    const user = await renderApp()
    expect(screen.getByText('5 מתכונים')).toBeInTheDocument()
    await user.type(searchBox(), 'כורכום')
    expect(cardTitles()).toEqual(['עוף בסיר עם אורז'])
    expect(screen.getByText('1 מתוך 5 מתכונים')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'ניקוי' }))
    expect(searchBox()).toHaveValue('')
    expect(cardTitles()).toHaveLength(5)
  })

  it('a top-level category shows all its recipes; a subcategory narrows them', async () => {
    const user = await renderApp()
    await pick(user, 'קטגוריה', 'קינוחים')
    expect(cardTitles()).toHaveLength(2) // the cake (in a subcategory) and the draft (in none)
    expect(group('קטגוריה').getByRole('radio', { name: 'קינוחים' })).toBeChecked()
    await pick(user, 'קינוחים:', 'קינוחים רגילים') // its subcategories appear once it is chosen
    expect(cardTitles()).toEqual(['עוגת שוקולד עם גנאש'])
    expect(group('קטגוריה').getByRole('radio', { name: 'קינוחים' })).toBeChecked() // still within desserts
    await pick(user, 'קינוחים:', 'כל הקינוחים')
    expect(cardTitles()).toHaveLength(2)
  })

  it('finds unclassified recipes, and shows drafts only or saved recipes only', async () => {
    const user = await renderApp()
    await pick(user, 'קטגוריה', 'לא מסווג')
    expect(cardTitles()).toEqual(['Oat and Date Granola Bars'])
    await pick(user, 'קטגוריה', 'הכול')
    await pick(user, 'מתכונים וטיוטות', 'טיוטות')
    expect(cardTitles()).toEqual(['כדורי תמרים'])
    await pick(user, 'מתכונים וטיוטות', 'מתכונים')
    expect(cardTitles()).toHaveLength(4)
  })

  it('combines a search with filters, and says clearly when nothing matches', async () => {
    const user = await renderApp()
    await pick(user, 'קטגוריה', 'קינוחים')
    await pick(user, 'מתכונים וטיוטות', 'מתכונים')
    await user.type(searchBox(), 'תמרים') // only the draft has dates: nothing saved matches
    expect(screen.getByText('לא נמצאו מתכונים שמתאימים לחיפוש ולסינון.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'ניקוי החיפוש והסינון' }))
    expect(cardTitles()).toHaveLength(5)
    expect(group('קטגוריה').getByRole('radio', { name: 'הכול' })).toBeChecked()
    expect(group('מתכונים וטיוטות').getByRole('radio', { name: 'הכול' })).toBeChecked()
  })

  it('typing a search on a recipe page goes back to the gallery with the results', async () => {
    const user = await renderApp()
    await user.click(gallery().getByRole('button', { name: /פיצה מבצק יוגורט/ }))
    await user.type(searchBox(), 'כורכום')
    expect(cardTitles()).toEqual(['עוף בסיר עם אורז'])
  })
})
