import { categoryLabel, categoryLook } from '../categoryLook'
import { creditedSource } from '../credit'
import { coverOf, pictureUrl } from '../media'
import type { Creator, Recipe } from '../types'
import { CookedBadge } from './CookedControl'
import Icon from './Icon'
import { MediaImage } from './MediaGallery'
import Placeholder from './Placeholder'

interface RecipeCardProps {
  recipe: Recipe
  onOpen: (id: number) => void // a function prop: the card reports the click, its parent decides what happens
  /** The badge was pressed: mark or unmark the recipe as cooked. */
  onToggleCooked: (recipe: Recipe) => void
  /** Its mark is being saved. */
  savingCooked: boolean
}

/** The card's credit, short: "@username", or the name when there is no username. */
function shortCredit(creator: Creator | undefined): string | null {
  if (creator === undefined) return null
  return creator.username !== null ? `@${creator.username}` : creator.name
}

// One tile of the gallery: the cover (a video's still too), or the category's drawing; the title; the
// category; the credit; and the "already cooked" badge. Two buttons side by side, never one inside the
// other: the card's button opens the recipe (Tab, Enter, Space work out of the box), the badge changes
// the mark. The reading order is the title first; CSS places the badge and the video mark on the
// picture's corners.
export default function RecipeCard({ recipe, onOpen, onToggleCooked, savingCooked }: RecipeCardProps) {
  const cover = coverOf(recipe)
  const picture = cover === undefined ? null : pictureUrl(cover)
  const credit = shortCredit(creditedSource(recipe.sources)?.creators[0])
  const titleId = `recipe-${recipe.id}-title`

  return (
    <div className="recipe-card" data-recipe-id={recipe.id}>
      <button type="button" className="recipe-card-open" onClick={() => onOpen(recipe.id)}>
        <span className="recipe-card-photo">
          {picture !== null ? <MediaImage src={picture} alt="" /> : <Placeholder category={recipe.category} />}
        </span>
        <span id={titleId} className="recipe-card-title" dir="auto">
          {recipe.title}
        </span>
        <span className="recipe-card-meta">
          <span className={`category-dot tone-${categoryLook(recipe.category).tone}`} aria-hidden="true" />
          {categoryLabel(recipe.category, recipe.subcategory)}
        </span>
        {cover?.kind === 'video' && (
          <span className="recipe-card-video">
            <Icon name="play" />
            <span className="visually-hidden">סרטון</span>
          </span>
        )}
        {(credit !== null || recipe.status === 'draft' || recipe.is_sample) && (
          <span className="recipe-card-foot">
            {credit !== null && <bdi className="recipe-card-credit">{credit}</bdi>}
            {recipe.status === 'draft' && <span className="badge-draft">טיוטה</span>}
            {recipe.is_sample && <span className="badge-sample">דוגמה</span>}
          </span>
        )}
      </button>
      <CookedBadge cooked={recipe.cooked} saving={savingCooked} describedBy={titleId} onToggle={() => onToggleCooked(recipe)} />
    </div>
  )
}
