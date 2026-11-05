import { useId } from 'react'
import {
  emptyIngredient,
  emptyIngredientGroup,
  moveItem,
  removeAt,
  replaceAt,
  type FieldErrors,
  type IngredientGroupForm,
  type IngredientRow,
} from '../editorForm'
import { ADDED_IN_REVIEW_LABEL, DERIVED_LABEL } from '../labels'
import FieldError from './FieldError'
import RowButtons from './RowButtons'

interface IngredientsEditorProps {
  groups: IngredientGroupForm[]
  errors: FieldErrors
  onChange: (groups: IngredientGroupForm[]) => void
}

// The ingredients part of the editor. It keeps no state of its own: it shows `groups` and
// reports every change through onChange, so the editor holds the one copy of the form.
export default function IngredientsEditor({ groups, errors, onChange }: IngredientsEditorProps) {
  // useId: a prefix that is unique on the page, for the ids that link fields to their error messages.
  const id = useId()
  const many = groups.length > 1

  function changeGroup(g: number, group: IngredientGroupForm) {
    onChange(replaceAt(groups, g, group))
  }
  function changeRow(g: number, i: number, row: IngredientRow) {
    changeGroup(g, { ...groups[g], ingredients: replaceAt(groups[g].ingredients, i, row) })
  }

  return (
    <fieldset className="editor-section">
      <legend className="section-title">מצרכים</legend>
      <p className="field-hint">
        כל מצרך בשורה משלו, כפי שהוא כתוב במתכון. בשדה הכמות מעתיקים את הכמות מתוך השורה, למשל "200 גרם" מתוך "200 גרם קמח".
        כשהמתכון לא נותן כמות, כמו ב"מלח ופלפל", משאירים את שדה הכמות ריק.
      </p>

      {groups.map((group, g) => {
        const where = many ? ` בקבוצה ${g + 1}` : ''
        const groupPath = `ingredient_groups.${g}`
        return (
          // The key is the row's temporary key from editorForm.ts, never its position.
          <div key={group.key} className="editor-group">
            <div className="editor-group-header">
              <label className="editor-field">
                <span className="field-label">{many ? `שם קבוצה ${g + 1} (לא חובה)` : 'שם הקבוצה (לא חובה)'}</span>
                <input
                  type="text"
                  dir="auto"
                  value={group.name}
                  placeholder='למשל "לבצק"'
                  aria-invalid={errors[groupPath] !== undefined}
                  aria-describedby={errors[groupPath] !== undefined ? `${id}-${groupPath}` : undefined}
                  onChange={(event) => changeGroup(g, { ...group, name: event.target.value })}
                />
              </label>
              <RowButtons
                label={many ? `קבוצת מצרכים ${g + 1}` : 'קבוצת המצרכים'}
                index={g}
                count={groups.length}
                onMove={(delta) => onChange(moveItem(groups, g, delta))}
                onRemove={() => onChange(removeAt(groups, g))}
              />
            </div>
            <FieldError id={`${id}-${groupPath}`} message={errors[groupPath]} />

            {group.ingredients.length > 0 && (
              // Column titles for sighted users; each input also has its own name for screen readers.
              <div className="ingredient-columns" aria-hidden="true">
                <span>שורת המצרך</span>
                <span>כמות, כפי שכתובה</span>
              </div>
            )}
            <ul className="editor-rows">
              {group.ingredients.map((row, i) => {
                const path = `${groupPath}.ingredients.${i}`
                const textError = errors[`${path}.text`] ?? errors[path]
                const quantityError = errors[`${path}.quantity`]
                return (
                  <li key={row.key} className="editor-row">
                    <div className="ingredient-inputs">
                      <input
                        type="text"
                        dir="auto"
                        aria-label={`מצרך ${i + 1}${where}`}
                        value={row.text}
                        placeholder="200 גרם קמח"
                        aria-invalid={textError !== undefined}
                        aria-describedby={
                          [textError !== undefined && `${id}-${path}.text`, row.derivedFrom !== null && `${id}-${path}.derived`].filter(Boolean).join(' ') ||
                          undefined
                        }
                        onChange={(event) => changeRow(g, i, { ...row, text: event.target.value })}
                      />
                      <input
                        type="text"
                        dir="auto"
                        className="quantity-input"
                        aria-label={`כמות במצרך ${i + 1}${where}`}
                        value={row.quantity}
                        placeholder="200 גרם"
                        aria-invalid={quantityError !== undefined}
                        aria-describedby={quantityError !== undefined ? `${id}-${path}.quantity` : undefined}
                        onChange={(event) => changeRow(g, i, { ...row, quantity: event.target.value })}
                      />
                      <RowButtons
                        label={`מצרך ${i + 1}${where}`}
                        index={i}
                        count={group.ingredients.length}
                        onMove={(delta) => changeGroup(g, { ...group, ingredients: moveItem(group.ingredients, i, delta) })}
                        onRemove={() => changeGroup(g, { ...group, ingredients: removeAt(group.ingredients, i) })}
                      />
                    </div>
                    {/* Added from a step (by the app's rule, or by you in review), not a line of the source's own list: said, never hidden. */}
                    {row.derivedFrom !== null && (
                      <p id={`${id}-${path}.derived`} className="derived-note">
                        <span className="derived-label">{row.addedInReview ? ADDED_IN_REVIEW_LABEL : DERIVED_LABEL}</span>{' '}
                        <q dir="auto">{row.derivedFrom}</q>
                      </p>
                    )}
                    <FieldError id={`${id}-${path}.text`} message={textError} />
                    <FieldError id={`${id}-${path}.quantity`} message={quantityError} />
                  </li>
                )
              })}
            </ul>
            <button
              type="button"
              className="add-button"
              aria-label={`הוספת מצרך${many ? ` לקבוצה ${g + 1}` : ''}`}
              onClick={() => changeGroup(g, { ...group, ingredients: [...group.ingredients, emptyIngredient()] })}
            >
              הוספת מצרך
            </button>
          </div>
        )
      })}

      <button type="button" className="add-button" onClick={() => onChange([...groups, emptyIngredientGroup()])}>
        הוספת קבוצת מצרכים
      </button>
    </fieldset>
  )
}
