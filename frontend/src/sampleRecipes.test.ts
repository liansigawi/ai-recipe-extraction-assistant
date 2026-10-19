import { describe, expect, it } from 'vitest'
import { sampleRecipes } from './sampleRecipes'

// Spot checks on the frontend's copy of the samples. The backend validates the full contract
// (backend/app/schemas.py) on its own copy; the two copies are kept identical until milestone 3.
describe('sample recipes', () => {
  it('have unique ids', () => {
    const ids = sampleRecipes.map((recipe) => recipe.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('quote every quantity exactly as written in its ingredient line', () => {
    for (const recipe of sampleRecipes) {
      for (const group of recipe.ingredient_groups) {
        for (const ingredient of group.ingredients) {
          if (ingredient.quantity !== null) {
            expect(ingredient.text).toContain(ingredient.quantity)
          }
        }
      }
    }
  })
})
