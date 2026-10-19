import type { Recipe } from '../types'
import CategoryChip from './CategoryChip'

interface RecipeCardProps {
  recipe: Recipe
  isSelected: boolean
  onSelect: (id: number) => void // a function prop: the card reports the click, its parent decides what happens
}

// One entry in the recipe list. A <button>, so it works with the keyboard (Tab, Enter, Space) out of the box.
export default function RecipeCard({ recipe, isSelected, onSelect }: RecipeCardProps) {
  const ingredientCount = recipe.ingredient_groups.reduce((total, group) => total + group.ingredients.length, 0)
  const stepCount = recipe.step_groups.reduce((total, group) => total + group.steps.length, 0)

  return (
    <button
      type="button"
      className="recipe-card"
      // aria-current tells assistive technology (and our CSS) which card is the one being shown.
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect(recipe.id)}
    >
      <span className="recipe-card-title" dir="auto">
        {recipe.title}
      </span>
      <CategoryChip category={recipe.category} />
      <span className="recipe-card-meta">
        {ingredientCount} מצרכים · {stepCount} שלבים
      </span>
    </button>
  )
}
