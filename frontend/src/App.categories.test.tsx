import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'

// Managing categories: the list with counts, editing, adding a subcategory and a top-level category.

async function openManager() {
  const user = userEvent.setup()
  const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories })
  render(<App />)
  await user.click(await screen.findByRole('button', { name: 'קטגוריות' }))
  await screen.findByRole('heading', { level: 2, name: 'קטגוריות' })
  return { user, api }
}

describe('managing categories', () => {
  it('lists every category with its description and how many recipes it holds', async () => {
    await openManager()
    const desserts = screen.getByRole('heading', { level: 3, name: 'קינוחים' }).closest('li')!
    expect(desserts).toHaveTextContent('מתכון אחד')
    expect(desserts).toHaveTextContent('עוגות, עוגיות, מאפים מתוקים וקינוחים')
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['קינוחים', 'בישולים', 'ארוחות קלילות'])
  })

  it('renames a category and changes its description; recipes in it show the new name', async () => {
    const { user, api } = await openManager()
    await user.click(screen.getByRole('button', { name: 'עריכת בישולים' }))
    const name = screen.getByLabelText('שם')
    await user.clear(name)
    await user.type(name, 'ארוחות בשריות')
    const description = screen.getByLabelText('תיאור (המודל מסווג לפיו)')
    await user.clear(description)
    await user.type(description, 'בשר או עוף')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    expect(await screen.findByText('הקטגוריה "ארוחות בשריות" נשמרה.')).toBeInTheDocument()
    expect(api.changes()).toEqual([
      { method: 'PUT', path: '/api/categories/2', body: { name: 'ארוחות בשריות', description: 'בשר או עוף' } },
    ])
    expect(screen.getByRole('heading', { level: 3, name: 'ארוחות בשריות' })).toBeInTheDocument()
    // The chicken recipe's card now carries the new name (same id: it never moved).
    await user.click(screen.getByRole('button', { name: 'חזרה למתכונים' }))
    const card = screen.getByRole('button', { name: /עוף בסיר עם אורז/ })
    expect(card).toHaveTextContent('ארוחות בשריות')
  })

  it('adds a subcategory, which the recipe editor then offers', async () => {
    const { user, api } = await openManager()
    await user.click(screen.getByRole('button', { name: '+ הוספת תת-קטגוריה ל"קינוחים"' }))
    await user.type(screen.getByLabelText('שם'), 'קינוחים בריאים')
    await user.type(screen.getByLabelText('תיאור (המודל מסווג לפיו)'), 'תמרים ושיבולת שועל')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    await screen.findByText('הקטגוריה "קינוחים בריאים" נשמרה.')
    expect(api.changes()[0]).toEqual({
      method: 'POST', path: '/api/categories', body: { name: 'קינוחים בריאים', description: 'תמרים ושיבולת שועל', parent_id: 1 },
    })
    const subs = screen.getByRole('list', { name: 'תת-קטגוריות של קינוחים' })
    expect(within(subs).getByRole('heading', { level: 4, name: 'קינוחים בריאים' })).toBeInTheDocument()

    // Back to the recipes: the chocolate cake's editor offers the new subcategory.
    await user.click(screen.getByRole('button', { name: 'חזרה למתכונים' }))
    await user.click(screen.getByRole('button', { name: /עוגת שוקולד עם גנאש/ }))
    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    expect(within(screen.getByLabelText('תת-קטגוריה')).getAllByRole('option').map((o) => o.textContent)).toEqual([
      'ללא', 'קינוחים בריאים',
    ])
  })

  it('adds a top-level category', async () => {
    const { user, api } = await openManager()
    await user.click(screen.getByRole('button', { name: 'הוספת קטגוריה ראשית' }))
    await user.type(screen.getByLabelText('שם'), 'משקאות')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    await screen.findByText('הקטגוריה "משקאות" נשמרה.')
    expect(api.changes()[0].body).toEqual({ name: 'משקאות', description: '', parent_id: null })
    expect(screen.getByRole('heading', { level: 3, name: 'משקאות' }).closest('li')).toHaveTextContent('אין תיאור')
  })

  it('says when a name is taken, and keeps the form open', async () => {
    const { user } = await openManager()
    await user.click(screen.getByRole('button', { name: 'הוספת קטגוריה ראשית' }))
    await user.type(screen.getByLabelText('שם'), 'קינוחים')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('כבר יש קטגוריה בשם הזה באותה רמה')
    expect(screen.getByLabelText('שם')).toHaveValue('קינוחים')
  })

  it('asks for a name before sending anything', async () => {
    const { user, api } = await openManager()
    await user.click(screen.getByRole('button', { name: 'הוספת קטגוריה ראשית' }))
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(screen.getByRole('alert')).toHaveTextContent('כתבו שם לקטגוריה.')
    expect(api.changes()).toEqual([])
  })

  it('asks before leaving a form with unsaved changes', async () => {
    const { user } = await openManager()
    await user.click(screen.getByRole('button', { name: 'עריכת קינוחים' }))
    await user.type(screen.getByLabelText('שם'), ' טעימים')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await user.click(screen.getByRole('button', { name: 'מתכונים' })) // the gallery
    expect(confirm).toHaveBeenCalled()
    expect(screen.getByLabelText('שם')).toHaveValue('קינוחים טעימים') // stayed
  })
})
