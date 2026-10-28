// Where the page is, kept in the address after "#" ("#/recipes/12"), so the browser's back button
// returns from a recipe to the gallery and a reload stays where it was. A few patterns, no library.

export type Route =
  | { kind: 'home' }
  | { kind: 'view'; recipeId: number }
  | { kind: 'edit'; recipeId: number }
  | { kind: 'create' }
  // url and start: a link from the gallery's import strip, read at once. Not kept in the address.
  | { kind: 'import'; url?: string; start?: boolean; focusText?: boolean }
  | { kind: 'categories' }

export function routeFromHash(hash: string): Route {
  const path = hash.replace(/^#\/?/, '')
  const recipe = /^recipes\/(\d+)(\/edit)?$/.exec(path)
  if (recipe !== null) {
    const recipeId = Number(recipe[1])
    return recipe[2] === undefined ? { kind: 'view', recipeId } : { kind: 'edit', recipeId }
  }
  if (path === 'new') return { kind: 'create' }
  if (path === 'import') return { kind: 'import' }
  if (path === 'categories') return { kind: 'categories' }
  return { kind: 'home' }
}

/** The address part for a route; '' for the gallery (the plain address). */
export function hashOf(route: Route): string {
  switch (route.kind) {
    case 'home':
      return ''
    case 'view':
      return `#/recipes/${route.recipeId}`
    case 'edit':
      return `#/recipes/${route.recipeId}/edit`
    case 'create':
      return '#/new'
    case 'import':
      return '#/import'
    case 'categories':
      return '#/categories'
  }
}
