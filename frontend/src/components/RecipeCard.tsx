import { coverOf, pictureUrl } from '../media'
import type { Recipe } from '../types'
import CategoryChip from './CategoryChip'
import { MediaImage } from './MediaGallery'

interface RecipeCardProps {
  recipe: Recipe
  isSelected: boolean
  onSelect: (id: number) => void // a function prop: the card reports the click, its parent decides what happens
}

// One entry in the recipe list. A <button>, so it works with the keyboard (Tab, Enter, Space) out of the box.
export default function RecipeCard({ recipe, isSelected, onSelect }: RecipeCardProps) {
  const ingredientCount = recipe.ingredient_groups.reduce((total, group) => total + group.ingredients.length, 0)
  const stepCount = recipe.step_groups.reduce((total, group) => total + group.steps.length, 0)
  const cover = coverOf(recipe)

  return (
    <button
      type="button"
      className="recipe-card"
      // aria-current tells assistive technology (and our CSS) which card is the one being shown.
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect(recipe.id)}
    >
      {/* The cover: decorative here (the title names the recipe); a placeholder keeps the cards aligned. */}
      <span className="recipe-card-cover">
        {cover !== undefined ? <MediaImage src={pictureUrl(cover)} alt="" /> : <span className="cover-placeholder" aria-hidden="true" />}
      </span>
      <span className="recipe-card-body">
        <span className="recipe-card-title" dir="auto">
          {recipe.title}
        </span>
        <span className="recipe-card-tags">
          {recipe.status === 'draft' && <span className="badge-draft">טיוטה</span>}
          <CategoryChip category={recipe.category} subcategory={recipe.subcategory} />
          {recipe.is_sample && <span className="badge-sample">דוגמה</span>}
        </span>
        <span className="recipe-card-meta">
          {ingredientCount} מצרכים · {stepCount} שלבים
        </span>
      </span>
    </button>
  )
}
