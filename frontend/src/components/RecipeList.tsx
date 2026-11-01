import type { Ref } from 'react'
import type { Recipe } from '../types'
import RecipeCard from './RecipeCard'

interface RecipeListProps {
  recipes: Recipe[]
  onOpen: (id: number) => void
  onToggleCooked?: (recipe: Recipe) => void
  /** The recipes whose "already cooked" mark is being saved. */
  savingCooked: ReadonlySet<number>
  /** Given while a search or a filter is on: an empty list then means "nothing matches". */
  onClearFilters?: () => void
  headingRef?: Ref<HTMLHeadingElement>
}

// The gallery: a tile for each recipe, as many in a row as fit (two on a phone).
export default function RecipeList({ recipes, onOpen, onToggleCooked, savingCooked, onClearFilters, headingRef }: RecipeListProps) {
  return (
    <section className="gallery" aria-labelledby="gallery-heading">
      {/* tabIndex={-1}: App can move focus here, e.g. after a recipe was deleted. */}
      <h2 id="gallery-heading" ref={headingRef} className="visually-hidden" tabIndex={-1}>
        המתכונים
      </h2>
      {recipes.length === 0 && onClearFilters !== undefined && (
        <div className="empty-state">
          <p>לא נמצאו מתכונים שמתאימים לחיפוש ולסינון.</p>
          <button type="button" className="button" onClick={onClearFilters}>
            ניקוי החיפוש והסינון
          </button>
        </div>
      )}
      {recipes.length === 0 && onClearFilters === undefined && <p className="empty-state">אין עדיין מתכונים במחברת.</p>}
      {recipes.length > 0 && (
        <ul className="recipe-grid">
          {recipes.map((recipe) => (
            // key: a stable, unique value per item, so React can match items between renders.
            <li key={recipe.id}>
              <RecipeCard recipe={recipe} onOpen={onOpen} onToggleCooked={onToggleCooked} savingCooked={savingCooked.has(recipe.id)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
