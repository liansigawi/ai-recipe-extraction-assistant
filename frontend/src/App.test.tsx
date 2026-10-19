import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { sampleRecipes } from './sampleRecipes'

// These tests use the app the way a person does: find things by their visible text and role, then click.

describe('App', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView
  })

  it('lists every recipe and shows the first one inside the main area', () => {
    render(<App recipes={sampleRecipes} />)

    const list = screen.getByRole('navigation')
    expect(within(list).getAllByRole('button')).toHaveLength(sampleRecipes.length)
    const main = screen.getByRole('main')
    expect(within(main).getByRole('article')).toBeInTheDocument()
    expect(within(main).getByRole('heading', { level: 2, name: 'עוגת שוקולד עם גנאש' })).toBeInTheDocument()
  })

  it('shows each card with its category and counts', () => {
    render(<App recipes={sampleRecipes} />)

    const card = screen.getByRole('button', { name: /עוגת שוקולד/ })
    expect(card).toHaveTextContent('קינוחים')
    expect(card).toHaveTextContent('9 מצרכים · 7 שלבים')
    expect(screen.getByRole('button', { name: /Granola/ })).toHaveTextContent('לא מסווג')
  })

  it('shows the recipe whose card was clicked and marks that card as current', async () => {
    const user = userEvent.setup()
    render(<App recipes={sampleRecipes} />)

    const pizzaCard = screen.getByRole('button', { name: /פיצה מבצק יוגורט/ })
    await user.click(pizzaCard)

    expect(screen.getByRole('heading', { level: 2, name: 'פיצה מבצק יוגורט' })).toBeInTheDocument()
    expect(pizzaCard).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('button', { name: /עוגת שוקולד/ })).not.toHaveAttribute('aria-current')
  })

  it('works with the keyboard alone: Enter and Space both choose a card', async () => {
    const user = userEvent.setup()
    render(<App recipes={sampleRecipes} />)

    await user.tab() // focus the first card
    await user.tab() // the second card
    await user.keyboard('{Enter}')
    expect(screen.getByRole('heading', { level: 2, name: 'עוף בסיר עם אורז' })).toBeInTheDocument()

    await user.tab() // the third card
    await user.keyboard(' ')
    expect(screen.getByRole('heading', { level: 2, name: 'פיצה מבצק יוגורט' })).toBeInTheDocument()
  })

  it('brings the chosen recipe into view only when it is off-screen', async () => {
    const user = userEvent.setup()
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView // jsdom has no layout, so we provide this
    render(<App recipes={sampleRecipes} />)

    // jsdom reports every element at the top of the screen, i.e. visible: no scrolling.
    await user.click(screen.getByRole('button', { name: /עוף בסיר/ }))
    expect(scrollIntoView).not.toHaveBeenCalled()

    // Pretend the title is below the visible area, as on a narrow screen.
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ top: 900, bottom: 940 } as DOMRect)
    await user.click(screen.getByRole('button', { name: /פיצה מבצק יוגורט/ }))
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' })
  })

  it('shows the first recipe when the recipes arrive after the first render', () => {
    // This is what will happen in milestone 3, when the list comes from the API.
    const { rerender } = render(<App recipes={[]} />)
    rerender(<App recipes={sampleRecipes} />)

    expect(screen.getByRole('heading', { level: 2, name: 'עוגת שוקולד עם גנאש' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /עוגת שוקולד/ })).toHaveAttribute('aria-current', 'true')
  })

  it('shows an empty state when there are no recipes', () => {
    render(<App recipes={[]} />)

    expect(screen.getByText('אין עדיין מתכונים במחברת.')).toBeInTheDocument()
    expect(screen.getByText('אין מתכון להצגה.')).toBeInTheDocument()
  })
})
