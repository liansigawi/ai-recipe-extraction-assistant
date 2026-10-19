import type { Recipe } from '../types'
import RecipeCard from './RecipeCard'

interface RecipeListProps {
  recipes: Recipe[]
  selectedId: number | null
  onSelect: (id: number) => void
}

export default function RecipeList({ recipes, selectedId, onSelect }: RecipeListProps) {
  if (recipes.length === 0) {
    return <p className="empty-state">אין עדיין מתכונים במחברת.</p>
  }

  return (
    <ul className="recipe-list">
      {recipes.map((recipe) => (
        // key: a stable, unique value per item, so React can match items between renders.
        <li key={recipe.id}>
          <RecipeCard recipe={recipe} isSelected={recipe.id === selectedId} onSelect={onSelect} />
        </li>
      ))}
    </ul>
  )
}
