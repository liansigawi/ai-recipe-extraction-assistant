import type { ReactNode, Ref } from 'react'
import { SOURCE_LABELS } from '../labels'
import type { IngredientGroup, Recipe, Source, StepGroup } from '../types'
import CategoryChip from './CategoryChip'
import OriginalText from './OriginalText'

// Dates in the page's language and the computer's own time zone; the API sends them in UTC.
const dateFormat = new Intl.DateTimeFormat('he-IL', { dateStyle: 'medium', timeStyle: 'short' })

interface RecipeViewProps {
  recipe: Recipe
  titleRef?: Ref<HTMLHeadingElement> // lets the parent reach the title element (App scrolls and focuses it)
  actions?: ReactNode // anything React can show; App passes the edit and delete buttons
}

// The cooking view: title and facts, then the ingredients ABOVE the numbered preparation steps.
// dir="auto" on recipe text lets an English recipe read left to right inside the right-to-left page.
export default function RecipeView({ recipe, titleRef, actions }: RecipeViewProps) {
  return (
    <article className="recipe-view">
      <div className="recipe-header">
        {/* tabIndex={-1}: not a Tab stop, but App can move focus here after saving or deleting. */}
        <h2 ref={titleRef} className="recipe-title" dir="auto" tabIndex={-1}>
          {recipe.title}
        </h2>
        {actions}
      </div>
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
        {recipe.servings !== null && <li dir="auto">{recipe.servings}</li>}
        {recipe.sources.map((source, index) => (
          <li key={index}>
            <SourceLabel source={source} />
          </li>
        ))}
        <li>
          עודכן <time dateTime={recipe.updated_at}>{dateFormat.format(new Date(recipe.updated_at))}</time>
        </li>
      </ul>
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

// The components below are used only by RecipeView, so they stay in this file and are not exported.
// Their lists use the position (index) as key: fine for read-only lists that never reorder.
// The editor's lists can change order, so they use stable keys instead (editorForm.ts).

function IngredientGroups({ groups }: { groups: IngredientGroup[] }) {
  return (
    <>
      {groups.map((group, groupIndex) => (
        <div key={groupIndex} className="ingredient-group">
          {group.name !== null && (
            <h4 className="group-title" dir="auto">
              {group.name}
            </h4>
          )}
          <ul className="ingredient-list" dir="auto">
            {group.ingredients.map((ingredient, index) => (
              <li key={index}>
                {ingredient.text}
                {/* The recipe gives no amount: say so, never invent one. The space keeps the words
                    apart for screen readers and copy-paste, not only visually. */}
                {ingredient.quantity === null && (
                  <>
                    {' '}
                    <span className="no-quantity">ללא כמות</span>
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

function StepGroups({ groups }: { groups: StepGroup[] }) {
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

function SourceLabel({ source }: { source: Source }) {
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
      {/* <bdi> isolates text whose direction is unknown, such as an English name inside Hebrew. */}
      {source.creators.map((creator, index) => (
        <span key={index}>
          {' · '}
          <bdi>{creator}</bdi>
        </span>
      ))}
    </span>
  )
}
