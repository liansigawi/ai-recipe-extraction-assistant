import { Fragment, type ReactNode, type Ref } from 'react'
import { creditedSource, postLink, profileUrl, shownName } from '../credit'
import { fromStepsLabel, SOURCE_LABELS } from '../labels'
import { coverOf, pictureUrl } from '../media'
import type { Creator, IngredientGroup, Recipe, Source, StepGroup } from '../types'
import { HEALTHY_LABEL } from '../categoryLook'
import CategoryChip from './CategoryChip'
import Icon from './Icon'
import MediaGallery, { MediaImage } from './MediaGallery'
import OriginalText from './OriginalText'
import Placeholder from './Placeholder'

// Dates in the page's language and the computer's own time zone; the API sends them in UTC.
const dateFormat = new Intl.DateTimeFormat('he-IL', { dateStyle: 'medium', timeStyle: 'short' })

interface RecipeViewProps {
  recipe: Recipe
  titleRef?: Ref<HTMLHeadingElement> // lets the parent reach the title element (App focuses it)
  toolbar?: ReactNode // anything React can show; App passes "back to the recipes", edit and delete
  cooked?: ReactNode // beside the title: App passes the "כבר הכנתי" control
  banner?: ReactNode // under the facts: the public copy's link to the recipe beside its original text
  onChange?: (recipe: Recipe) => void // after a change to its media (without it, the gallery only shows)
}

// The cooking view: title and facts, then the ingredients ABOVE the numbered preparation steps.
// dir="auto" on recipe text lets an English recipe read left to right inside the right-to-left page.
export default function RecipeView({ recipe, titleRef, toolbar, cooked, banner, onChange }: RecipeViewProps) {
  const cover = coverOf(recipe)
  const picture = cover === undefined ? null : pictureUrl(cover)
  return (
    <article className="recipe-view">
      {toolbar}
      {/* The card's picture, large (decorative: the gallery below names each picture), or the category's drawing. */}
      <div className={picture !== null ? 'recipe-cover' : 'recipe-cover recipe-cover-empty'}>
        {picture !== null ? <MediaImage src={picture} alt="" /> : <Placeholder category={recipe.category} />}
      </div>
      <div className="recipe-header">
        {/* tabIndex={-1}: not a Tab stop, but App can move focus here after opening or saving. */}
        <h2 ref={titleRef} className="recipe-title" dir="auto" tabIndex={-1}>
          {recipe.title}
        </h2>
        {cooked}
      </div>
      <CreditLine sources={recipe.sources} />
      {recipe.is_sample && (
        <p className="sample-note">
          מתכון דוגמה: הומצא כדי להדגים את המחברת. הוא לא מבוסס על מתכון אמיתי, וגם לא על הקישורים מאינסטגרם ששלחתם. אפשר
          לערוך או למחוק אותו.
        </p>
      )}
      {recipe.status === 'draft' && (
        <p className="draft-note">
          טיוטה מיובאת שעוד לא נבדקה
          {recipe.issues.length > 0 && ` (${recipe.issues.length} נקודות לבדיקה)`}. לחצו "בדיקה ושמירה" כדי להשוות אותה לטקסט
          המקורי ולשמור כמתכון.
        </p>
      )}
      <ul className="recipe-facts">
        <li>
          <CategoryChip category={recipe.category} subcategory={recipe.subcategory} />
        </li>
        {recipe.healthy === true && (
          <li>
            <span className="chip chip-healthy">
              <Icon name="leaf" />
              {HEALTHY_LABEL}
            </span>
          </li>
        )}
        {recipe.servings !== null && <li dir="auto">{recipe.servings}</li>}
        {recipe.sources.map((source, index) => (
          <li key={index}>
            {/* The credited source's creators are already under the title. */}
            <SourceLabel source={source} withCreators={source !== creditedSource(recipe.sources)} />
          </li>
        ))}
        <li>
          עודכן <time dateTime={recipe.updated_at}>{dateFormat.format(new Date(recipe.updated_at))}</time>
        </li>
      </ul>
      {banner}
      <MediaGallery recipe={recipe} onChange={onChange} />
      {recipe.original !== null && <OriginalText original={recipe.original} />}

      <section className="recipe-section">
        <h3 className="section-title">מצרכים</h3>
        <IngredientGroups groups={recipe.ingredient_groups} />
      </section>

      <section className="recipe-section">
        <h3 className="section-title">אופן ההכנה</h3>
        <StepGroups groups={recipe.step_groups} />
      </section>

      {recipe.notes.length > 0 && (
        <section className="recipe-section">
          <h3 className="section-title">הערות</h3>
          <ul className="note-list" dir="auto">
            {recipe.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </section>
      )}
    </article>
  )
}

// The lists below are also shown by the public copy's comparison page (SourceComparison).
// Their lists use the position (index) as key: fine for read-only lists that never reorder.
// The editor's lists can change order, so they use stable keys instead (editorForm.ts).

/** Above a group without a name that follows a named group. */
export const MORE_INGREDIENTS = 'מצרכים נוספים'

/** markQuantities: each line's quantity, as the backend read it from the line, is highlighted in it.
 * explainAdded: a line added in review says so, with the step's sentence to open (a demonstration's result). */
export function IngredientGroups({ groups, markQuantities = false, explainAdded = false }: { groups: IngredientGroup[]; markQuantities?: boolean; explainAdded?: boolean }) {
  return (
    <>
      {groups.map((group, groupIndex) => (
        <div key={groupIndex} className="ingredient-group">
          {group.name !== null ? (
            <h4 className="group-title" dir="auto">
              {group.name}
            </h4>
          ) : (
            // A group without a name after a named one would read as part of it: a display heading only, not its name.
            groups.slice(0, groupIndex).some((before) => before.name !== null) && <h4 className="group-title group-title-unnamed">{MORE_INGREDIENTS}</h4>
          )}
          <ul className="ingredient-list" dir="auto">
            {group.ingredients.map((ingredient, index) => (
              <li key={index}>
                {markQuantities ? <MarkedLine text={ingredient.text} quantity={ingredient.quantity} /> : ingredient.text}
                {/* The recipe gives no amount: say so, never invent one. The space keeps the words
                    apart for screen readers and copy-paste, not only visually. */}
                {ingredient.quantity === null && (
                  <>
                    {' '}
                    <span className="no-quantity">ללא כמות</span>
                  </>
                )}
                {/* A line added from a step (by the app, or approved in review): labeled, with the step's sentence on hover. */}
                {explainAdded && ingredient.added_in_review && ingredient.derived_from != null ? (
                  <details className="added-from-point">
                    <summary>נוסף בעקבות התרעה</summary>
                    מתוך ההוראות: <q dir="auto">{ingredient.derived_from}</q>
                  </details>
                ) : ingredient.derived_from != null && (
                  <>
                    {' '}
                    <span className="derived-label" title={ingredient.derived_from}>
                      {fromStepsLabel(ingredient)}
                    </span>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}

/** The line with its quantity in a <mark> (the quantity is always a piece of the line, by the contract). */
function MarkedLine({ text, quantity }: { text: string; quantity: string | null }) {
  const at = quantity === null ? -1 : text.indexOf(quantity)
  if (quantity === null || at < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <mark className="quantity-mark">{quantity}</mark>
      {text.slice(at + quantity.length)}
    </>
  )
}

export function StepGroups({ groups }: { groups: StepGroup[] }) {
  return (
    <>
      {groups.map((group, groupIndex) => (
        <div key={groupIndex} className="step-group">
          {group.name !== null && (
            <h4 className="group-title" dir="auto">
              {group.name}
            </h4>
          )}
          {/* <ol> numbers the steps. Numbering restarts in each group, so alternative methods stay apart. */}
          <ol className="step-list" dir="auto">
            {group.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      ))}
    </>
  )
}

/** Under the title: "מאת ריטה קדוש (@ritakadosh_) · לפוסט המקורי באינסטגרם", from the editable credit. */
function CreditLine({ sources }: { sources: Source[] }) {
  const credited = creditedSource(sources)
  const post = postLink(sources)
  if (credited === undefined && post === undefined) return null
  return (
    <p className="credit-line">
      {credited !== undefined && (
        <>
          מאת{' '}
          {credited.creators.map((creator, index) => (
            <Fragment key={index}>
              {index > 0 && ', '}
              <CreatorName creator={creator} />
            </Fragment>
          ))}
        </>
      )}
      {post !== undefined && post.url !== null && (
        <>
          {credited !== undefined && ' · '}
          <a href={post.url} target="_blank" rel="noreferrer">
            {post.kind === 'instagram' ? 'לפוסט המקורי באינסטגרם' : post.kind === 'website' ? 'לדף המתכון' : 'למקור'}
          </a>
        </>
      )}
    </p>
  )
}

/** "ריטה קדוש (@ritakadosh_)", with the username linking to the Instagram profile; the username alone
 * when there is no other name. */
export function CreatorName({ creator }: { creator: Creator }) {
  const name = shownName(creator)
  const handle =
    creator.username !== null ? (
      <a href={profileUrl(creator.username)} target="_blank" rel="noreferrer" dir="ltr">
        @{creator.username}
      </a>
    ) : null
  return (
    <span className="creator">
      {/* <bdi> isolates text whose direction is unknown, such as an English name inside Hebrew. */}
      {name !== null && <bdi className="creator-name">{name}</bdi>}
      {name !== null && handle !== null && <> ({handle})</>}
      {name === null && handle}
    </span>
  )
}

function SourceLabel({ source, withCreators }: { source: Source; withCreators: boolean }) {
  const label = SOURCE_LABELS[source.kind]
  return (
    <span>
      מקור:{' '}
      {source.url !== null ? (
        // rel="noreferrer": the opened page cannot control this tab or see where the visit came from.
        <a href={source.url} target="_blank" rel="noreferrer">
          {label}
        </a>
      ) : (
        label
      )}
      {withCreators &&
        source.creators.map((creator, index) => (
          <span key={index}>
            {' · '}
            <CreatorName creator={creator} />
          </span>
        ))}
    </span>
  )
}
