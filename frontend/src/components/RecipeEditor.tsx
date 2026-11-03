import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { ApiError, createRecipe, errorMessage, updateRecipe } from '../api'
import {
  emptyNote,
  emptySource,
  errorsFromApi,
  formToInput,
  moveItem,
  recipeToForm,
  removeAt,
  replaceAt,
  validateForm,
  type FieldErrors,
  type NoteRow,
  type RecipeForm,
  type SourceRow,
} from '../editorForm'
import { HEALTHY_LABEL } from '../categoryLook'
import { SOURCE_KINDS, SOURCE_LABELS } from '../labels'
import type { Category, Recipe, RecipeStatus } from '../types'
import FieldError from './FieldError'
import IngredientsEditor from './IngredientsEditor'
import MediaGallery from './MediaGallery'
import OriginalText from './OriginalText'
import ReviewIssues from './ReviewIssues'
import RowButtons from './RowButtons'
import StepsEditor from './StepsEditor'

// "קינוח בריא": decided either way, or left undecided (the model, or you, may not know).
const HEALTHY_CHOICES: { value: RecipeForm['healthy']; label: string }[] = [
  { value: 'yes', label: 'כן' },
  { value: 'no', label: 'לא' },
  { value: '', label: 'לא נקבע' },
]

interface RecipeEditorProps {
  /** The recipe to edit; undefined for a new recipe. */
  recipe?: Recipe
  categories: Category[]
  onSaved: (recipe: Recipe) => void
  onCancel: () => void
  /** Told whenever the form starts or stops differing from what was opened. */
  onDirtyChange: (dirty: boolean) => void
}

/** The form as the API would receive it, as text: equal text means nothing to save. */
const savedShape = (form: RecipeForm, status: RecipeStatus) => JSON.stringify(formToInput(form, status).input)

// A controlled form: every input shows a value from `form` state, and every keystroke
// updates that state. React, not the browser, is the one place the current text lives.
//
// For an imported draft it is the review screen: the original text and the points to check
// are shown above the form, and saving is explicit: "save as recipe", or "save draft" to
// continue later.
export default function RecipeEditor({ recipe, categories, onSaved, onCancel, onDirtyChange }: RecipeEditorProps) {
  const id = useId()
  const isDraft = recipe?.status === 'draft'
  const keptStatus: RecipeStatus = isDraft ? 'draft' : 'saved'
  // A function given to useState runs on the first render only: the form starts from the
  // recipe once, and later renders keep the person's changes.
  const [form, setForm] = useState(() => recipeToForm(recipe))
  const [openedShape] = useState(() => savedShape(form, keptStatus))
  const [checkFields, setCheckFields] = useState(false) // turned on by the first attempt to save
  const [serverErrors, setServerErrors] = useState<FieldErrors>({})
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [refusedSaves, setRefusedSaves] = useState(0)
  const formRef = useRef<HTMLFormElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)

  // Derived on every render, not stored: once the person has tried to save, the form is checked
  // again on each change, so a message disappears as soon as its field is fixed.
  const errors: FieldErrors = { ...(checkFields ? validateForm(form) : {}), ...serverErrors }
  const errorCount = Object.keys(errors).length
  const category = categories.find((option) => String(option.id) === form.category_id)

  // When the editor opens, put the cursor in the title. An effect with [] runs once, after the first render.
  // A draft's review starts at the top instead: the original text and the points to check come first,
  // and focusing the title would scroll them away.
  useEffect(() => {
    if (isDraft) headingRef.current?.focus()
    else titleInputRef.current?.focus()
  }, [isDraft])

  // After a refused save, move the cursor to the first field with a problem.
  useEffect(() => {
    if (refusedSaves > 0) {
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
    }
  }, [refusedSaves])

  // Every change to the form goes through here.
  function update(next: RecipeForm) {
    setForm(next)
    setServerErrors({}) // the server's verdict was about the previous content
    onDirtyChange(savedShape(next, keptStatus) !== openedShape)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault() // stop the browser's own form submission, which would reload the page
    // Enter in a field, or the form's submit button: a draft stays a draft; a recipe is saved.
    void save(keptStatus)
  }

  async function save(status: RecipeStatus) {
    if (saving) return
    if (
      isDraft &&
      status === 'saved' &&
      form.issues.length > 0 &&
      !window.confirm(`נשארו ${form.issues.length} נקודות שלא סומנו כטופלו. לשמור כמתכון בכל זאת?`)
    ) {
      return
    }
    setCheckFields(true)
    setSaveError(null)
    if (Object.keys(validateForm(form)).length > 0) {
      setRefusedSaves((count) => count + 1)
      return
    }
    const { input, pathMap } = formToInput(form, status)
    setSaving(true)
    try {
      // await: wait for the server's answer without freezing the page.
      const saved = recipe === undefined ? await createRecipe(input) : await updateRecipe(recipe.id, input)
      onSaved(saved) // the parent closes the editor and shows the saved recipe
    } catch (error) {
      setSaving(false)
      const fieldErrors = error instanceof ApiError ? errorsFromApi(error.code, error.details, pathMap) : null
      if (fieldErrors !== null) {
        setServerErrors(fieldErrors)
        setRefusedSaves((count) => count + 1)
      } else {
        setSaveError(errorMessage(error))
      }
    }
  }

  // aria-describedby takes a list of ids; this one links a field to its hint and its error, if any.
  const describedBy = (...ids: (string | false)[]) => ids.filter(Boolean).join(' ') || undefined

  return (
    // noValidate: the browser's own error bubbles are turned off, so the form's messages are the only ones.
    <form ref={formRef} className="recipe-editor" onSubmit={handleSubmit} noValidate aria-labelledby={`${id}-heading`}>
      <h2 ref={headingRef} id={`${id}-heading`} className="recipe-title" tabIndex={-1}>
        {recipe === undefined ? 'מתכון חדש' : isDraft ? 'בדיקת טיוטה' : 'עריכת מתכון'}
      </h2>
      {recipe?.is_sample && <p className="sample-note">זה מתכון דוגמה שהומצא. גם אחרי עריכה הוא יישאר מסומן כדוגמה.</p>}
      {isDraft && (
        <p className="draft-note">
          טיוטה מיובאת: השוו אותה לטקסט המקורי, תקנו מה שצריך, ושמרו כמתכון. אפשר גם לשמור כטיוטה ולהמשיך אחר כך.
        </p>
      )}
      {recipe?.original != null && <OriginalText original={recipe.original} open={isDraft} sticky={isDraft} />}
      {isDraft && <ReviewIssues issues={form.issues} onChange={(issues) => update({ ...form, issues })} />}
      {/* What was saved from the post, to look at while reviewing; the cover and removal are in the recipe view. */}
      {isDraft && recipe !== undefined && recipe.media.length > 0 && <MediaGallery recipe={recipe} />}

      <div className="editor-basics">
        <div className="editor-field editor-field-wide">
          <label htmlFor={`${id}-title`} className="field-label">
            כותרת
          </label>
          <input
            ref={titleInputRef}
            id={`${id}-title`}
            type="text"
            dir="auto"
            required
            value={form.title}
            aria-invalid={errors.title !== undefined}
            aria-describedby={describedBy(errors.title !== undefined && `${id}-title-error`)}
            onChange={(event) => update({ ...form, title: event.target.value })}
          />
          <FieldError id={`${id}-title-error`} message={errors.title} />
        </div>

        <div className="editor-field">
          <label htmlFor={`${id}-category`} className="field-label">
            קטגוריה
          </label>
          {/* Only existing categories can be chosen; there is no way to type a new one here. */}
          <select
            id={`${id}-category`}
            value={form.category_id}
            aria-invalid={errors.category_id !== undefined}
            aria-describedby={describedBy(`${id}-category-hint`, errors.category_id !== undefined && `${id}-category-error`)}
            onChange={(event) => update({ ...form, category_id: event.target.value, subcategory_id: '', healthy: '' })}
          >
            <option value="">לא מסווג</option>
            {categories.map((option) => (
              <option key={option.id} value={String(option.id)}>
                {option.name}
              </option>
            ))}
          </select>
          <p id={`${id}-category-hint`} className="field-hint">
            בוחרים מהקטגוריות הקיימות, או משאירים "לא מסווג".
          </p>
          <FieldError id={`${id}-category-error`} message={errors.category_id} />
        </div>

        {category !== undefined && category.subcategories.length > 0 && (
          <div className="editor-field">
            <label htmlFor={`${id}-subcategory`} className="field-label">
              תת-קטגוריה
            </label>
            <select
              id={`${id}-subcategory`}
              value={form.subcategory_id}
              aria-invalid={errors.subcategory_id !== undefined}
              aria-describedby={describedBy(errors.subcategory_id !== undefined && `${id}-subcategory-error`)}
              onChange={(event) => update({ ...form, subcategory_id: event.target.value })}
            >
              <option value="">ללא</option>
              {category.subcategories.map((option) => (
                <option key={option.id} value={String(option.id)}>
                  {option.name}
                </option>
              ))}
            </select>
            <FieldError id={`${id}-subcategory-error`} message={errors.subcategory_id} />
          </div>
        )}

        {/* The healthy style is its own choice, beside the dessert's type: a frozen dessert can be healthy too. */}
        {(category?.healthy_style === true || form.healthy !== '') && (
          <fieldset className="editor-field healthy-field" aria-describedby={describedBy(`${id}-healthy-hint`, errors.healthy !== undefined && `${id}-healthy-error`)}>
            <legend className="field-label">{HEALTHY_LABEL}</legend>
            <div className="choice-row">
              {HEALTHY_CHOICES.map((choice) => (
                <label key={choice.value} className="choice">
                  <input type="radio" name={`${id}-healthy`} checked={form.healthy === choice.value} onChange={() => update({ ...form, healthy: choice.value })} />
                  {choice.label}
                </label>
              ))}
            </div>
            <p id={`${id}-healthy-hint`} className="field-hint">
              הסגנון האישי שלך לסידור, לא הערכה תזונתית: קינוח שבנוי בעיקר על שיבולת שועל, קוטג׳ או יוגורט, אגוזים, קמח שקדים, תמרים, פירות
              או דבש. לפי המתכון כולו.
            </p>
            <FieldError id={`${id}-healthy-error`} message={errors.healthy} />
          </fieldset>
        )}

        <div className="editor-field">
          <label htmlFor={`${id}-servings`} className="field-label">
            כמות מנות (לא חובה)
          </label>
          <input
            id={`${id}-servings`}
            type="text"
            dir="auto"
            placeholder='למשל "12 פרוסות"'
            value={form.servings}
            onChange={(event) => update({ ...form, servings: event.target.value })}
          />
        </div>
      </div>

      <IngredientsEditor
        groups={form.ingredient_groups}
        errors={errors}
        onChange={(groups) => update({ ...form, ingredient_groups: groups })}
      />
      <StepsEditor groups={form.step_groups} errors={errors} onChange={(groups) => update({ ...form, step_groups: groups })} />
      <NotesEditor notes={form.notes} onChange={(notes) => update({ ...form, notes })} />
      <SourcesEditor sources={form.sources} errors={errors} onChange={(sources) => update({ ...form, sources })} />

      <div className="editor-footer">
        {checkFields && errorCount > 0 && (
          // role="alert": a screen reader announces this message as soon as it appears.
          <div role="alert" className="form-alert">
            <p>לא נשמר: {errorCount === 1 ? 'יש שדה אחד לתקן' : `יש ${errorCount} שדות לתקן`}. השדות מסומנים באדום.</p>
            {Object.keys(serverErrors).length > 0 && (
              <ul>
                {Object.entries(serverErrors).map(([path, message]) => (
                  <li key={path}>{message}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {saveError !== null && (
          <p role="alert" className="form-alert">
            {saveError}
          </p>
        )}
        {isDraft ? (
          <div className="button-row">
            {/* type="button": only a deliberate click saves a draft as a recipe, never Enter in a field. */}
            <button type="button" className="button-primary" onClick={() => void save('saved')}>
              {saving ? 'שומר…' : 'שמירה כמתכון'}
            </button>
            <button type="submit" className="button">
              שמירת טיוטה
            </button>
            <button type="button" className="button" onClick={onCancel}>
              ביטול
            </button>
          </div>
        ) : (
          <div className="button-row">
            <button type="submit" className="button-primary">
              {saving ? 'שומר…' : 'שמירה'}
            </button>
            <button type="button" className="button" onClick={onCancel}>
              ביטול
            </button>
          </div>
        )}
      </div>
    </form>
  )
}

// The two short sections below are used only by RecipeEditor, so they stay in this file.

function NotesEditor({ notes, onChange }: { notes: NoteRow[]; onChange: (notes: NoteRow[]) => void }) {
  return (
    <fieldset className="editor-section">
      <legend className="section-title">הערות</legend>
      <p className="field-hint">תחליפים, אחסון, ציוד או הגשה: רק מה שכתוב במתכון.</p>
      {notes.length > 0 && (
        <ul className="editor-rows">
          {notes.map((note, i) => (
            <li key={note.key} className="editor-row">
              <div className="step-inputs">
                <textarea
                  dir="auto"
                  rows={2}
                  aria-label={`הערה ${i + 1}`}
                  value={note.text}
                  onChange={(event) => onChange(replaceAt(notes, i, { ...note, text: event.target.value }))}
                />
                <RowButtons
                  label={`הערה ${i + 1}`}
                  index={i}
                  count={notes.length}
                  onMove={(delta) => onChange(moveItem(notes, i, delta))}
                  onRemove={() => onChange(removeAt(notes, i))}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="add-button" onClick={() => onChange([...notes, emptyNote()])}>
        הוספת הערה
      </button>
    </fieldset>
  )
}

interface SourcesEditorProps {
  sources: SourceRow[]
  errors: FieldErrors
  onChange: (sources: SourceRow[]) => void
}

function SourcesEditor({ sources, errors, onChange }: SourcesEditorProps) {
  const id = useId()
  return (
    <fieldset className="editor-section">
      <legend className="section-title">מקורות</legend>
      <p className="field-hint">
        מאיפה המתכון הגיע: סוג המקור, קישור אם יש, ומי יצר אותו. כל יוצר בשמו ובשם המשתמש שלו באינסטגרם, מופרדים בפסיקים: "ריטה קדוש
        @ritakadosh_, @alehonline". אפשר לכתוב כאן גם מי שהפוסט מקרדט; מה שנשלף מהפוסט נשמר בנפרד, בטקסט המקורי.
      </p>
      {sources.length > 0 && (
        <ul className="editor-rows">
          {sources.map((source, s) => {
            const urlError = errors[`sources.${s}.url`]
            const change = (next: SourceRow) => onChange(replaceAt(sources, s, next))
            return (
              <li key={source.key} className="editor-row">
                <div className="source-inputs">
                  <select
                    aria-label={`סוג מקור ${s + 1}`}
                    value={source.kind}
                    // The options come from SOURCE_KINDS, so the chosen value is always one of them.
                    onChange={(event) => change({ ...source, kind: event.target.value as SourceRow['kind'] })}
                  >
                    {SOURCE_KINDS.map((kind) => (
                      <option key={kind} value={kind}>
                        {SOURCE_LABELS[kind]}
                      </option>
                    ))}
                  </select>
                  <input
                    type="url"
                    dir="ltr"
                    aria-label={`קישור למקור ${s + 1}`}
                    placeholder="https://"
                    value={source.url}
                    aria-invalid={urlError !== undefined}
                    aria-describedby={urlError !== undefined ? `${id}-${s}-url` : undefined}
                    onChange={(event) => change({ ...source, url: event.target.value })}
                  />
                  <input
                    type="text"
                    dir="auto"
                    aria-label={`יוצרים במקור ${s + 1}`}
                    placeholder="שם @שם_משתמש"
                    value={source.creators}
                    onChange={(event) => change({ ...source, creators: event.target.value })}
                  />
                  <RowButtons
                    label={`מקור ${s + 1}`}
                    index={s}
                    count={sources.length}
                    onMove={(delta) => onChange(moveItem(sources, s, delta))}
                    onRemove={() => onChange(removeAt(sources, s))}
                  />
                </div>
                <FieldError id={`${id}-${s}-url`} message={urlError} />
              </li>
            )
          })}
        </ul>
      )}
      <button type="button" className="add-button" onClick={() => onChange([...sources, emptySource()])}>
        הוספת מקור
      </button>
    </fieldset>
  )
}
