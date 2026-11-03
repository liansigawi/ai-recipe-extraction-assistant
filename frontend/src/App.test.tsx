import { act, render, screen, within } from '@testing-library/react'
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
  await screen.findByRole('region', { name: 'המתכונים' }) // findBy... waits until the first load has finished
  return api
}

const recipeHeading = (name: string) => screen.getByRole('heading', { level: 2, name })
// The gallery of recipe cards.
const gallery = () => within(screen.getByRole('region', { name: 'המתכונים' }))
const card = (name: string | RegExp) => gallery().getByRole('button', { name: typeof name === 'string' ? new RegExp(name) : name })

async function openRecipe(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(card(name))
  return recipeHeading(name)
}

/** What the browser does on its back button: the address changes, then "popstate". */
function browserBack(address: string) {
  act(() => {
    window.history.replaceState(null, '', address)
    window.dispatchEvent(new PopStateEvent('popstate'))
  })
}

describe('loading the notebook', () => {
  it('shows a loading message, then the gallery of recipes from the API', async () => {
    const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories })
    render(<App />)

    expect(screen.getByText('טוען את המתכונים…')).toBeInTheDocument()
    expect(await screen.findByRole('region', { name: 'המתכונים' })).toBeInTheDocument()
    expect(gallery().getAllByRole('listitem')).toHaveLength(sampleRecipes.length)
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
    expect(await screen.findByRole('region', { name: 'המתכונים' })).toBeInTheDocument()
  })
})

describe('browsing', () => {
  it('opens on the gallery: a card for every recipe, and no recipe open yet', async () => {
    await renderApp()

    expect(gallery().getAllByRole('listitem')).toHaveLength(sampleRecipes.length)
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'מתכונים' })).toHaveAttribute('aria-current', 'page')
  })

  it('shows on each card its category, whether it was cooked, its credit, and the invented samples', async () => {
    await renderApp()

    expect(card(CAKE)).toHaveTextContent('קינוחים')
    const badge = within(card(CAKE).closest('li')!).getByRole('button', { name: 'כבר הכנתי' })
    expect(badge).toHaveAttribute('aria-pressed', 'false') // every recipe starts unmarked
    expect(badge).toHaveTextContent('טרם הכנתי')
    expect(card(CAKE)).toHaveTextContent('דוגמה')
    expect(card(/Granola/)).toHaveTextContent('לא מסווג')
    expect(card(/Granola/)).toHaveTextContent('Example Kitchen') // the credit, short
  })

  it('opens the recipe whose card was clicked, and "כל המתכונים" goes back to that card', async () => {
    const user = userEvent.setup()
    await renderApp()

    const title = await openRecipe(user, 'פיצה מבצק יוגורט')
    expect(title).toHaveFocus()
    expect(window.location.hash).toBe(`#/recipes/${sampleRecipes[2].id}`) // the browser's back button can return
    expect(screen.getByRole('main')).toHaveTextContent('הוא לא מבוסס על מתכון אמיתי, וגם לא על הקישורים מאינסטגרם ששלחתם')

    await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
    expect(card('פיצה מבצק יוגורט')).toHaveFocus()
    expect(window.location.hash).toBe('')
  })

  it("the browser's back and forward buttons move between the gallery and a recipe", async () => {
    const user = userEvent.setup()
    await renderApp()
    await openRecipe(user, 'עוף בסיר עם אורז')

    browserBack('/')
    expect(screen.getByRole('region', { name: 'המתכונים' })).toBeInTheDocument()
    expect(card('עוף בסיר עם אורז')).toHaveFocus()

    browserBack(`#/recipes/${sampleRecipes[1].id}`) // forward again
    expect(recipeHeading('עוף בסיר עם אורז')).toHaveFocus()
  })

  it('a reload stays on the recipe the address names; an unknown one shows the gallery', async () => {
    window.history.replaceState(null, '', `#/recipes/${sampleRecipes[2].id}`)
    fakeApi({ recipes: sampleRecipes, categories: sampleCategories })
    const view = render(<App />)
    expect(await screen.findByRole('heading', { level: 2, name: 'פיצה מבצק יוגורט' })).toBeInTheDocument()
    view.unmount()

    window.history.replaceState(null, '', '#/recipes/999')
    render(<App />)
    expect(await screen.findByRole('region', { name: 'המתכונים' })).toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })

  it('works with the keyboard: Enter and Space open a card', async () => {
    const user = userEvent.setup()
    await renderApp()

    card('עוף בסיר עם אורז').focus()
    await user.keyboard('{Enter}')
    expect(recipeHeading('עוף בסיר עם אורז')).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
    await user.tab() // from the chicken's card to its badge
    await user.tab() // and to the next card
    expect(card('פיצה מבצק יוגורט')).toHaveFocus()
    await user.keyboard(' ')
    expect(recipeHeading('פיצה מבצק יוגורט')).toBeInTheDocument()
  })

  it('a recipe opens at the top of the page, and the gallery comes back where it was scrolled to', async () => {
    const user = userEvent.setup()
    const scrollTo = vi.spyOn(window, 'scrollTo')
    await renderApp()
    Object.defineProperty(window, 'scrollY', { value: 640, configurable: true })
    try {
      await openRecipe(user, 'פיצה מבצק יוגורט')
      expect(scrollTo).toHaveBeenLastCalledWith(0, 0)
      await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
      expect(scrollTo).toHaveBeenLastCalledWith(0, 640)
    } finally {
      Object.defineProperty(window, 'scrollY', { value: 0, configurable: true })
    }
  })

  it('shows an empty state when there are no recipes', async () => {
    await renderApp([])

    expect(screen.getByText('אין עדיין מתכונים במחברת.')).toBeInTheDocument()
    expect(screen.queryByRole('search', { name: 'סינון מתכונים' })).not.toBeInTheDocument()
  })
})

describe('creating a recipe', () => {
  const startNewRecipe = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole('button', { name: 'לכתוב מתכון חדש' }))

  it('sends exactly what was typed, then shows the saved recipe, first in the gallery', async () => {
    const user = userEvent.setup()
    const api = await renderApp()

    await startNewRecipe(user)
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
          healthy: null,
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
          status: 'saved',
          issues: [],
        },
      },
    ])
    expect(recipeHeading('עוגת תפוזים')).toHaveFocus()
    expect(screen.getByText('מלח').closest('li')).toHaveTextContent('ללא כמות')
    expect(screen.getByRole('checkbox', { name: 'כבר הכנתי' })).not.toBeChecked() // a new recipe starts unmarked

    await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
    const firstCard = gallery().getAllByRole('listitem')[0]
    expect(firstCard).toHaveTextContent('עוגת תפוזים')
    expect(card('עוגת תפוזים')).toHaveFocus()
    expect(firstCard).not.toHaveTextContent('דוגמה')
  })

  it('offers only the existing categories, or none', async () => {
    const user = userEvent.setup()
    await renderApp()
    await startNewRecipe(user)

    const options = within(screen.getByLabelText('קטגוריה')).getAllByRole('option')
    expect(options.map((option) => option.textContent)).toEqual(['לא מסווג', 'קינוחים', 'בישולים', 'ארוחות קלילות'])
    expect(screen.getByLabelText('קטגוריה')).toHaveValue('') // a new recipe starts unclassified
  })

  it('checks the form before sending: a title is required and a quantity must be quoted from its line', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await startNewRecipe(user)
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
    await startNewRecipe(user)
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
    await startNewRecipe(user)
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
    await openRecipe(user, CAKE)
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
      healthy: null,
      servings: cake.servings,
      ingredient_groups: cake.ingredient_groups, // untouched content goes back exactly as it was
      step_groups: cake.step_groups,
      notes: cake.notes,
      sources: cake.sources,
      status: 'saved',
      issues: [], // and never the cooked mark: only its own control changes it
    })
    expect(recipeHeading('עוגת שוקולד מריר')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
    expect(card('עוגת שוקולד מריר')).toHaveFocus()
  })

  it('moves an ingredient up with its button', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await openRecipe(user, CAKE)
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
    await openRecipe(user, CAKE)

    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    await user.click(screen.getByRole('button', { name: 'ביטול' }))
    expect(confirm).not.toHaveBeenCalled() // nothing changed, nothing to lose
    expect(recipeHeading(CAKE)).toHaveFocus()

    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    await user.type(screen.getByLabelText('כותרת'), ' חדשה')
    await user.click(screen.getByRole('button', { name: 'מתכונים' })) // the gallery: asks first
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('כותרת')).toHaveValue(`${CAKE} חדשה`) // "stay" keeps the editor

    const editing = window.location.hash
    browserBack(`#/recipes/${sampleRecipes[0].id}`) // the browser's back button asks too
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(screen.getByLabelText('כותרת')).toHaveValue(`${CAKE} חדשה`)
    expect(window.location.hash).toBe(editing) // and the address is put back

    confirm.mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: 'ביטול' }))
    expect(recipeHeading(CAKE)).toBeInTheDocument()
    expect(api.changes()).toEqual([])
  })
})

describe('deleting a recipe', () => {
  it('asks in the page first, then deletes and shows the gallery without it', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await openRecipe(user, CAKE)

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    expect(screen.getByRole('group', { name: /למחוק את המתכון/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'לא, להשאיר' })).toHaveFocus() // the safe choice
    await user.click(screen.getByRole('button', { name: 'לא, להשאיר' }))
    expect(api.changes()).toEqual([])

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    await user.click(screen.getByRole('button', { name: 'כן, למחוק' }))

    expect(await screen.findByText('המתכון נמחק.')).toBeInTheDocument()
    expect(api.changes()).toEqual([{ method: 'DELETE', path: '/api/recipes/1', body: undefined }])
    expect(screen.getByRole('heading', { level: 2, name: 'המתכונים' })).toHaveFocus()
    expect(gallery().queryByRole('button', { name: /עוגת שוקולד/ })).not.toBeInTheDocument()
    expect(window.location.hash).toBe('')
  })

  it('says why a delete failed and keeps the recipe', async () => {
    const user = userEvent.setup()
    const api = await renderApp()
    await openRecipe(user, CAKE)
    api.answerNextWith(500, { error: { code: 'internal_error', message: 'Something went wrong on the server.', details: null } })

    await user.click(screen.getByRole('button', { name: 'מחיקה' }))
    await user.click(screen.getByRole('button', { name: 'כן, למחוק' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('הפעולה נכשלה: Something went wrong on the server.')
    expect(recipeHeading(CAKE)).toBeInTheDocument()
  })
})
