import { describe, expect, it } from 'vitest'
import { hashOf, routeFromHash, type Route } from './route'

describe('routes in the address', () => {
  it('go there and back', () => {
    const routes: Route[] = [
      { kind: 'home' },
      { kind: 'view', recipeId: 12 },
      { kind: 'edit', recipeId: 3 },
      { kind: 'create' },
      { kind: 'import' },
      { kind: 'categories' },
      { kind: 'source', recipeId: 6 },
      { kind: 'about' },
    ]
    for (const route of routes) expect(routeFromHash(hashOf(route))).toEqual(route)
  })

  it('an unknown or broken address is the gallery', () => {
    for (const hash of ['', '#', '#/', '#/recipes/', '#/recipes/abc', '#/nothing', '#recipes/x/edit/2']) {
      expect(routeFromHash(hash)).toEqual({ kind: 'home' })
    }
  })

  it("an import's link is not kept in the address", () => {
    expect(hashOf({ kind: 'import', url: 'https://www.instagram.com/p/x/', start: true })).toBe('#/import')
  })
})
