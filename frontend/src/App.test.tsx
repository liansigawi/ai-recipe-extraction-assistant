import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'

// These tests use the app the way a person does: find things by their visible text and role,
// then click and type. The page talks to a fake backend (test/fakeApi.ts) that answers from memory.

const CAKE = 'עוגת שוקולד עם גנאש'

async function renderApp(recipes = sampleRecipes) {
  const api = fakeApi({ recipes, categories: sampleCategories })
  render(<App />)
  await screen.findByRole('navigation') // findBy... waits until the first load has finished
  return api
}

const recipeHeading = (name: string) => screen.getByRole('heading', { level: 2, name })
// The recipe cards: the list inside the navigation area.
const recipeList = () => within(within(screen.getByRole('navigation')).getByRole('list'))

describe('loading the notebook', () => {
  it('shows a loading message, then the recipes from the API', async () => {
    const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories })
    render(<App />)

    expect(screen.getByText('טוען את המתכונים…')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 2, name: CAKE })).toBeInTheDocument()
    expect(api.calls.map((call) => `${call.method} ${call.path}`).sort()).toEqual(['GET /api/categories', 'GET /api/recipes'])
  })

  it('explains when the server cannot be reached, and tries again on request', async () => {
    const user = userEvent.setup()
    const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories })
    api.setOffline(true)
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('אין חיבור לשרת')
    api.setOffline(false)
    await user.click(screen.getByRole('button', { name: 'נסו שוב' }))
    expect(await screen.findByRole('heading', { level: 2, name: CAKE })).toBeInTheDocument()
  })
})

describe('browsing', () => {
  it('lists every recipe and shows the first one inside the main area', async () => {
    await renderApp()

    expect(recipeList().getAllByRole('button')).toHaveLength(sampleRecipes.length)
    const main = screen.getByRole('main')
    expect(within(main).getByRole('article')).toBeInTheDocument()
    expect(within(main).getByRole('heading', { level: 2, name: CAKE })).toBeInTheDocument()
  })

  it('shows each card with its category and counts, and labels the invented samples', async () => {
    await renderApp()

    const card = screen.getByRole('button', { name: /עוגת שוקולד/ })
    expect(card).toHaveTextContent('קינוחים')
    expect(card).toHaveTextContent('דוגמה')
    expect(card).toHaveTextContent('9 מצרכים · 7 שלבים')
    expect(screen.getByRole('button', { name: /Granola/ })).toHaveTextContent('לא מסווג')
    expect(screen.getByRole('main')).toHaveTextContent('הוא לא מבוסס על מתכון אמיתי, וגם לא על הקישורים מאינסטגרם ששלחתם')
  })

  it('shows the recipe whose card was clicked and marks that card as current', async () => {
    const user = userEvent.setup()
    await renderApp()

    const pizzaCard = screen.getByRole('button', { name: /פיצה מבצק יוגורט/ })
    await user.click(pizzaCard)

    expect(recipeHeading('פיצה מבצק יוגורט')).toBeInTheDocument()
    expect(pizzaCard).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /עוגת שוקולד/ })).not.toHaveAttribute('aria-current')
  })

  it('works with the keyboard alone: Enter and Space both choose a card', async () => {
    const user = userEvent.setup()
    await renderApp()

    await user.tab() // the "new recipe" button
    await user.tab() // the first card
    await user.tab() // the second card
    await user.keyboard('{Enter}')
    expect(recipeHeading('עוף בסיר עם אורז')).toBeInTheDocument()

    await user.tab() // the third card
    await user.keyboard(' ')
    expect(recipeHeading('פיצה מבצק יוגורט')).toBeInTheDocument()
  })

  it('brings the chosen recipe into view only when it is off-screen', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView // jsdom has no layout, so we provide this
    try {
      await renderApp()

      // jsdom reports every element at the top of the screen, i.e. visible: no scrolling.
      await user.click(screen.getByRole('button', { name: /עוף בסיר/ }))
      expect(scrollIntoView).not.toHaveBeenCalled()

      // Pretend the title is below the visible area, as on a narrow screen.
      vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top: 900, bottom: 940 } as DOMRect)
      await user.click(screen.getByRole('button', { name: /פיצה מבצק יוגורט/ }))
      expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' })
    } finally {
      delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView
    }
  })

  it('shows an empty state when there are no recipes', async () => {
    await renderApp([])

    expect(screen.getByText('אין עדיין מתכונים במחברת.')).toBeInTheDocument()
    expect(screen.getByText(/אין מתכון להצגה/)).toBeInTheDocument()
  })
})

describe('creating a recipe', () => {
  it('sends exactly what was typed, then shows the saved recipe first in the list', async () => {
    const user = userEvent.setup()
    const api = await renderApp()

    await user.click(screen.getByRole('button', { name: 'מתכון חדש' }))
    expect(screen.getByLabelText('כותרת')).toHaveFocus()
    await user.type(screen.getByLabelText('כותרת'), 'עוגת תפוזים')
    await user.selectOptions(screen.getByLabelText('קטגוריה'), 'קינוחים')
    await user.type(screen.getByLabelText('מצרך 1'), '2 כוסות קמח')
    await user.type(screen.getByLabelText('כמות במצרך 1'), '2 כוסות')
    await user.click(screen.getByRole('button', { name: 'הוספת מצרך' }))
    await user.type(screen.getByLabelText('מצרך 2'), 'מלח')
    await user.type(screen.getByLabelText('שלב 1'), 'מערבבים הכול.')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    expect(await screen.findByText('המתכון נשמר.')).toBeInTheDocument()
    expect(api.changes()).toEqual([
      {
        method: 'POST',
        path: '/api/recipes',
        body: {
          title: 'עוגת תפוזים',
          category_id: 1,
          subcategory_id: null,
          servings: null,
          ingredient_groups: [
            {
              name: null,
              ingredients: [
                { text: '2 כוסות קמח', quantity: '2 כוסות' },
                { text: 'מלח', quantity: null }, // no quantity typed: stays "no quantity"
              ],
            },
          ],
          step_groups: [{ name: null, steps: ['מערבבים הכול.'] }],
          notes: [],
          sources: [],
        },
      },
    ])
    expect(recipeHeading('עוגת תפוזים')).toHaveFocus()
    expect(screen.getByText('מלח').closest('li')).toHaveTextContent('ללא כמות')
    const firstCard = recipeList().getAllByRole('button')[0]
    expect(firstCard).toHaveTextContent('עוגת תפוזים')
    expect(firstCard).toHaveAttribute('aria-current', 'true')
    expect(firstCard).not.toHaveTextContent('דוגמה')
  })

  it('offers only the existing categories, or none', async () => {
    const user = userEvent.setup()
    await renderApp()
    await user.click(screen.getByRole('button', { name: 'מתכון חדש' }))

    const options = within(screen.getByLabelText('קטגוריה')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['לא מסווג', 'קינוחים', 'בישולים', 'ארוחות קלילות'])
    expect(screen.getByLabelText('קטגוריה')).toHaveValue('') // a new recipe starts unclassified
  })

  it('checks the form before sending: a title is required and a quantity must be quoted from its line', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await user.click(screen.getByRole('button', { name: 'מתכון חדש' }))
    await user.type(screen.getByLabelText('מצרך 1'), '200 גרם קמח')
    await user.type(screen.getByLabelText('כמות במצרך 1'), '2') // cut out of "200": not the amount

    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    expect(api.changes()).toEqual([]) // nothing was sent
    expect(screen.getByRole('alert')).toHaveTextContent('יש 2 שדות לתקן')
    expect(screen.getByLabelText('כותרת')).toHaveFocus() // the first field with a problem
    expect(screen.getByLabelText('כותרת')).toHaveAccessibleDescription('כתבו כותרת למתכון.')
    expect(screen.getByLabelText('כמות במצרך 1')).toHaveAccessibleDescription(/הכמות צריכה להופיע בשורת המצרך/)

    // Messages disappear as the fields are fixed.
    await user.type(screen.getByLabelText('כותרת'), 'לחם')
    await user.clear(screen.getByLabelText('כמות במצרך 1'))
    await user.type(screen.getByLabelText('כמות במצרך 1'), '200 גרם')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(await screen.findByText('המתכון נשמר.')).toBeInTheDocument()
  })

  it("shows the server's objection next to the field it is about", async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await user.click(screen.getByRole('button', { name: 'מתכון חדש' }))
    await user.type(screen.getByLabelText('כותרת'), 'חביתה')
    await user.click(screen.getByRole('button', { name: 'הוספת מצרך' }))
    await user.type(screen.getByLabelText('מצרך 2'), '3 ביצים') // row 1 stays empty and is not sent

    // The server refers to the first ingredient it received, which is the form's second row.
    api.answerNextWith(422, {
      error: {
        code: 'invalid_request',
        message: 'The request is not valid.',
        details: [{ loc: ['body', 'ingredient_groups', 0, 'ingredients', 0], msg: 'Value error, not allowed', type: 'value_error' }],
      },
    })
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    const row = await screen.findByLabelText('מצרך 2')
    expect(row).toHaveAttribute('aria-invalid', 'true')
    expect(row).toHaveAccessibleDescription('השרת דחה את הערך: Value error, not allowed')
    expect(screen.getByLabelText('מצרך 1')).toHaveAttribute('aria-invalid', 'false')
    expect(screen.getByRole('heading', { level: 2, name: 'מתכון חדש' })).toBeInTheDocument() // still editing
  })

  it('keeps what was typed when the server cannot be reached, and says why', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await user.click(screen.getByRole('button', { name: 'מתכון חדש' }))
    await user.type(screen.getByLabelText('כותרת'), 'מרק עדשים')

    api.setOffline(true)
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('אין חיבור לשרת')
    expect(screen.getByLabelText('כותרת')).toHaveValue('מרק עדשים')

    api.setOffline(false)
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(await screen.findByRole('heading', { level: 2, name: 'מרק עדשים' })).toBeInTheDocument()
  })
})

describe('editing a recipe', () => {
  it('starts from the saved content, and saving sends the change and nothing else', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await user.click(screen.getByRole('button', { name: 'עריכה' }))

    const title = screen.getByLabelText('כותרת')
    expect(title).toHaveValue(CAKE)
    expect(screen.getByLabelText('מצרך 2 בקבוצה 1')).toHaveValue('150 גרם חמאה מומסת')
    expect(screen.getByLabelText('כמות במצרך 2 בקבוצה 1')).toHaveValue('150 גרם')
    expect(screen.getByLabelText('קטגוריה')).toHaveValue('1')
    await user.clear(title)
    await user.type(title, 'עוגת שוקולד מריר')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    expect(await screen.findByText('המתכון נשמר.')).toBeInTheDocument()
    const [save] = api.changes()
    expect(save.method).toBe('PUT')
    expect(save.path).toBe('/api/recipes/1')
    const cake = sampleRecipes[0]
    expect(save.body).toEqual({
      title: 'עוגת שוקולד מריר',
      category_id: 1,
      subcategory_id: null,
      servings: cake.servings,
      ingredient_groups: cake.ingredient_groups, // untouched content goes back exactly as it was
      step_groups: cake.step_groups,
      notes: cake.notes,
      sources: cake.sources,
    })
    expect(recipeHeading('עוגת שוקולד מריר')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /עוגת שוקולד מריר/ })).toHaveAttribute('aria-current', 'true')
  })

  it('moves an ingredient up with its button', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await user.click(screen.getByRole('button', { name: 'עריכה' }))

    await user.click(screen.getByRole('button', { name: 'הזזת מצרך 2 בקבוצה 1 למעלה' }))
    expect(screen.getByLabelText('מצרך 1 בקבוצה 1')).toHaveValue('150 גרם חמאה מומסת')
    await user.click(screen.getByRole('button', { name: 'שמירה' }))

    await screen.findByText('המתכון נשמר.')
    const body = api.changes()[0].body as { ingredient_groups: { ingredients: { text: string }[] }[] }
    expect(body.ingredient_groups[0].ingredients.slice(0, 2).map((ingredient) => ingredient.text)).toEqual([
      '150 גרם חמאה מומסת',
      '200 גרם שוקולד מריר',
    ])
  })

  it('asks before throwing away unsaved changes, and not when there are none', async () => {
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const api = await renderApp()

    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    await user.click(screen.getByRole('button', { name: 'ביטול' }))
    expect(confirm).not.toHaveBeenCalled() // nothing changed, nothing to lose
    expect(recipeHeading(CAKE)).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    await user.type(screen.getByLabelText('כותרת'), ' חדשה')
    await user.click(screen.getByRole('button', { name: /עוף בסיר/ })) // another recipe: asks first
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('כותרת')).toHaveValue(`${CAKE} חדשה`) // "stay" keeps the editor

    confirm.mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: 'ביטול' }))
    expect(recipeHeading(CAKE)).toBeInTheDocument()
    expect(api.changes()).toEqual([])
  })
})

describe('deleting a recipe', () => {
  it('asks in the page first, then deletes and shows the next recipe', async () => {
    const user = userEvent.setup()
    const api = await renderApp()

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    expect(screen.getByRole('group', { name: /למחוק את המתכון/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'לא, להשאיר' })).toHaveFocus() // the safe choice
    await user.click(screen.getByRole('button', { name: 'לא, להשאיר' }))
    expect(api.changes()).toEqual([])

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    await user.click(screen.getByRole('button', { name: 'כן, למחוק' }))

    expect(await screen.findByText('המתכון נמחק.')).toBeInTheDocument()
    expect(api.changes()).toEqual([{ method: 'DELETE', path: '/api/recipes/1', body: undefined }])
    expect(recipeHeading('עוף בסיר עם אורז')).toHaveFocus()
    expect(screen.queryByRole('button', { name: /עוגת שוקולד/ })).not.toBeInTheDocument()
  })

  it('says why a delete failed and keeps the recipe', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    api.answerNextWith(500, { error: { code: 'internal_error', message: 'Something went wrong on the server.', details: null } })

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    await user.click(screen.getByRole('button', { name: 'כן, למחוק' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('הפעולה נכשלה: Something went wrong on the server.')
    expect(screen.getByRole('button', { name: /עוגת שוקולד/ })).toBeInTheDocument()
  })
})
