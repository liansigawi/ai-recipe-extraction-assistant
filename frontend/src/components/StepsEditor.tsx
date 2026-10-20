import { useId } from 'react'
import {
  emptyStep,
  emptyStepGroup,
  moveItem,
  removeAt,
  replaceAt,
  type FieldErrors,
  type StepGroupForm,
} from '../editorForm'
import FieldError from './FieldError'
import RowButtons from './RowButtons'

interface StepsEditorProps {
  groups: StepGroupForm[]
  errors: FieldErrors
  onChange: (groups: StepGroupForm[]) => void
}

// The preparation steps, in groups. Like IngredientsEditor, it keeps no state of its own.
export default function StepsEditor({ groups, errors, onChange }: StepsEditorProps) {
  const id = useId()
  const many = groups.length > 1

  function changeGroup(g: number, group: StepGroupForm) {
    onChange(replaceAt(groups, g, group))
  }

  return (
    <fieldset className="editor-section">
      <legend className="section-title">אופן ההכנה</legend>
      <p className="field-hint">
        שלב בכל תיבה, לפי הסדר. כשהמתכון נותן דרכים חלופיות בקטעים נפרדים (למשל "בסיר לחץ" ו"בסיר רגיל"), כל דרך היא קבוצה
        עם הכותרת שלה.
      </p>

      {groups.map((group, g) => {
        const where = many ? ` בקבוצה ${g + 1}` : ''
        const groupPath = `step_groups.${g}`
        return (
          <div key={group.key} className="editor-group">
            <div className="editor-group-header">
              <label className="editor-field">
                <span className="field-label">{many ? `כותרת קבוצה ${g + 1} (לא חובה)` : 'כותרת הקבוצה (לא חובה)'}</span>
                <input
                  type="text"
                  dir="auto"
                  value={group.name}
                  placeholder='למשל "בסיר לחץ"'
                  aria-invalid={errors[groupPath] !== undefined}
                  aria-describedby={errors[groupPath] !== undefined ? `${id}-${groupPath}` : undefined}
                  onChange={(event) => changeGroup(g, { ...group, name: event.target.value })}
                />
              </label>
              <RowButtons
                label={many ? `קבוצת שלבים ${g + 1}` : 'קבוצת השלבים'}
                index={g}
                count={groups.length}
                onMove={(delta) => onChange(moveItem(groups, g, delta))}
                onRemove={() => onChange(removeAt(groups, g))}
              />
            </div>
            <FieldError id={`${id}-${groupPath}`} message={errors[groupPath]} />

            <ol className="editor-rows">
              {group.steps.map((row, i) => {
                const path = `${groupPath}.steps.${i}`
                return (
                  <li key={row.key} className="editor-row">
                    <div className="step-inputs">
                      <span className="step-number" aria-hidden="true">
                        {i + 1}.
                      </span>
                      <textarea
                        dir="auto"
                        rows={2}
                        aria-label={`שלב ${i + 1}${where}`}
                        value={row.text}
                        aria-invalid={errors[path] !== undefined}
                        aria-describedby={errors[path] !== undefined ? `${id}-${path}` : undefined}
                        onChange={(event) => changeGroup(g, { ...group, steps: replaceAt(group.steps, i, { ...row, text: event.target.value }) })}
                      />
                      <RowButtons
                        label={`שלב ${i + 1}${where}`}
                        index={i}
                        count={group.steps.length}
                        onMove={(delta) => changeGroup(g, { ...group, steps: moveItem(group.steps, i, delta) })}
                        onRemove={() => changeGroup(g, { ...group, steps: removeAt(group.steps, i) })}
                      />
                    </div>
                    <FieldError id={`${id}-${path}`} message={errors[path]} />
                  </li>
                )
              })}
            </ol>
            <button
              type="button"
              className="add-button"
              aria-label={`הוספת שלב${many ? ` לקבוצה ${g + 1}` : ''}`}
              onClick={() => changeGroup(g, { ...group, steps: [...group.steps, emptyStep()] })}
            >
              הוספת שלב
            </button>
          </div>
        )
      })}

      <button type="button" className="add-button" onClick={() => onChange([...groups, emptyStepGroup()])}>
        הוספת קבוצת שלבים
      </button>
    </fieldset>
  )
}
