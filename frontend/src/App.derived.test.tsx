import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'
import { reviewChanges } from './processing'
import { fakeApi } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Recipe } from './types'

// A line the app added from the preparation ("מעט שמן לטיגון", backend/app/extraction/derived.py): labeled on
// the recipe and in the editor, kept with where it comes from when the recipe is saved, removable as any line.
const SENTENCE = 'מחממים מעט שמן במחבת.'
const OIL = { text: 'מעט שמן לטיגון', quantity: 'מעט', derived_from: SENTENCE }
const [cake, ...others] = sampleRecipes
const omelette: Recipe = {
  ...cake,
  title: 'חביתת ירק',
  ingredient_groups: [{ name: null, ingredients: [{ text: '3 ביצים', quantity: '3' }, OIL] }],
  step_groups: [{ name: null, steps: [`${SENTENCE} יוצקים פנימה את הביצים.`] }],
}

async function openRecipe() {
  const user = userEvent.setup()
  const api = fakeApi({ recipes: [omelette, ...others], categories: sampleCategories })
  render(<App />)
  await user.click(await screen.findByRole('button', { name: /חביתת ירק/ }))
  return { user, api }
}

describe('an ingredient line derived from the preparation', () => {
  it('is labeled on the recipe, with its sentence', async () => {
    await openRecipe()
    const label = screen.getByText('מופיע בהוראות ההכנה')
    expect(label.closest('li')).toHaveTextContent('מעט שמן לטיגון')
    expect(label).toHaveAttribute('title', SENTENCE)
  })

  it('is labeled in the editor and saved with where it comes from; removed, it is gone', async () => {
    const { user, api } = await openRecipe()
    await user.click(screen.getByRole('button', { name: 'עריכה' }))
    const line = screen.getByRole('textbox', { name: 'מצרך 2' })
    expect(line).toHaveValue('מעט שמן לטיגון')
    expect(line).toHaveAccessibleDescription(`מופיע בהוראות ההכנה ${SENTENCE}`)
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    expect(api.changes()[0].body).toMatchObject({ ingredient_groups: [{ name: null, ingredients: [{ text: '3 ביצים', quantity: '3' }, OIL] }] })

    await user.click(await screen.findByRole('button', { name: 'עריכה' }))
    await user.click(screen.getByRole('button', { name: 'הסרת מצרך 2' }))
    expect(screen.queryByText('מופיע בהוראות ההכנה')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'שמירה' }))
    const [, second] = api.changes()
    expect(second.body).toMatchObject({ ingredient_groups: [{ name: null, ingredients: [{ text: '3 ביצים', quantity: '3' }] }] })
    expect(await screen.findByRole('button', { name: 'עריכה' })).toBeInTheDocument() // back on the saved recipe
    expect(screen.queryByText('מעט שמן לטיגון')).not.toBeInTheDocument()
  })

  it('shows as derived in what review changed', () => {
    const draft = { title: 'חביתת ירק', servings: null, category: null, subcategory: null, ingredient_groups: [{ name: null, ingredients: [{ text: '3 ביצים', quantity: '3' }] }], step_groups: omelette.step_groups, notes: [], issues: [], saved_at: omelette.created_at }
    const change = reviewChanges(draft, omelette).changed.find((part) => part.part === 'מצרכים')
    expect(change?.lines).toEqual([{ kind: 'added', text: 'מעט שמן לטיגון · כמות: מעט · מופיע בהוראות ההכנה' }])
  })
})
