import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { createCategory, errorMessage, updateCategory } from '../api'
import type { Category, CategoryInput, Recipe, Subcategory } from '../types'

const MAX_NAME = 60 // the backend's limits (MAX_CATEGORY_NAME, MAX_CATEGORY_DESCRIPTION)
const MAX_DESCRIPTION = 600
const DISCARD_QUESTION = 'לסגור את הטופס? השינויים שלא נשמרו יאבדו.'

// Which form is open: editing one category, or a new one (top-level, or under a parent). One at a time.
type Open = { kind: 'edit'; id: number } | { kind: 'new'; parentId: number | null } | null

interface CategoryManagerProps {
  categories: Category[]
  /** For the counts beside each category. */
  recipes: Recipe[]
  /** Called after a save: loads the categories (and the recipes, for their category names) again. */
  onChanged: () => Promise<void>
  onClose: () => void
  /** Tells the page whether a form has unsaved changes, so leaving asks first. */
  onDirtyChange: (dirty: boolean) => void
}

export default function CategoryManager({ categories, recipes, onChanged, onClose, onDirtyChange }: CategoryManagerProps) {
  const id = useId()
  const [open, setOpen] = useState<Open>(null)
  const [dirty, setDirty] = useState(false)
  const [status, setStatus] = useState('')
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  function changeDirty(value: boolean) {
    setDirty(value)
    onDirtyChange(value)
  }

  /** Opens a form, asking first if another one has unsaved changes. */
  function openForm(next: Open) {
    if (dirty && !window.confirm(DISCARD_QUESTION)) return
    changeDirty(false)
    setOpen(next)
    setStatus('')
  }

  async function save(input: CategoryInput) {
    if (open?.kind === 'edit') await updateCategory(open.id, input)
    else await createCategory({ ...input, parent_id: open?.kind === 'new' ? open.parentId : null })
    await onChanged()
    changeDirty(false)
    setOpen(null)
    setStatus(`הקטגוריה "${input.name.trim()}" נשמרה.`)
  }

  function count(category: Subcategory, isSub: boolean): number {
    return recipes.filter((recipe) => (isSub ? recipe.subcategory?.id : recipe.category?.id) === category.id).length
  }

  function formFor(category: Subcategory | null, legend: string) {
    return (
      <CategoryForm
        legend={legend}
        initial={{ name: category?.name ?? '', description: category?.description ?? '' }}
        onSave={save}
        onCancel={() => openForm(null)}
        onDirtyChange={changeDirty}
      />
    )
  }

  function summary(category: Subcategory, isSub: boolean) {
    const recipesIn = count(category, isSub)
    return (
      <div className="category-summary">
        <div className="category-summary-text">
          {isSub ? <h4 className="category-name">{category.name}</h4> : <h3 className="category-name">{category.name}</h3>}
          <span className="category-count">{recipesIn === 1 ? 'מתכון אחד' : `${recipesIn} מתכונים`}</span>
          <p className="category-description">{category.description ?? 'אין תיאור. המודל יסווג לכאן רק לפי השם.'}</p>
        </div>
        <button type="button" className="button" aria-label={`עריכת ${category.name}`} onClick={() => openForm({ kind: 'edit', id: category.id })}>
          עריכה
        </button>
      </div>
    )
  }

  return (
    <section className="category-manager" aria-labelledby={`${id}-heading`}>
      <div className="manager-header">
        <h2 id={`${id}-heading`} ref={headingRef} tabIndex={-1} className="recipe-title">
          קטגוריות
        </h2>
        <button type="button" className="button" onClick={onClose}>
          חזרה למתכונים
        </button>
      </div>
      <p className="field-hint">
        המודל בוחר רק מתוך הקטגוריות כאן, לפי התיאורים: כתבו בכל תיאור מה שייך לקטגוריה, וזה ישפיע על הסיווג בייבוא הבא. שינוי שם או
        תיאור לא מזיז אף מתכון; את שיוך המתכונים משנים בעריכת המתכון.
      </p>
      <output className="notice">{status}</output>

      <ul className="category-tree">
        {categories.map((category) => (
          <li key={category.id} className="category-node">
            {open?.kind === 'edit' && open.id === category.id ? formFor(category, `עריכת הקטגוריה "${category.name}"`) : summary(category, false)}
            <ul className="subcategory-list" aria-label={`תת-קטגוריות של ${category.name}`}>
              {category.subcategories.map((sub) => (
                <li key={sub.id}>
                  {open?.kind === 'edit' && open.id === sub.id ? formFor(sub, `עריכת תת-הקטגוריה "${sub.name}"`) : summary(sub, true)}
                </li>
              ))}
              <li>
                {open?.kind === 'new' && open.parentId === category.id ? (
                  formFor(null, `תת-קטגוריה חדשה ב"${category.name}"`)
                ) : (
                  <button type="button" className="add-button" onClick={() => openForm({ kind: 'new', parentId: category.id })}>
                    + הוספת תת-קטגוריה ל"{category.name}"
                  </button>
                )}
              </li>
            </ul>
          </li>
        ))}
      </ul>

      {open?.kind === 'new' && open.parentId === null ? (
        formFor(null, 'קטגוריה ראשית חדשה')
      ) : (
        <div className="button-row">
          <button type="button" className="button-primary" onClick={() => openForm({ kind: 'new', parentId: null })}>
            הוספת קטגוריה ראשית
          </button>
        </div>
      )}
    </section>
  )
}

interface CategoryFormProps {
  legend: string
  initial: { name: string; description: string }
  onSave: (input: CategoryInput) => Promise<void>
  onCancel: () => void
  onDirtyChange: (dirty: boolean) => void
}

function CategoryForm({ legend, initial, onSave, onCancel, onDirtyChange }: CategoryFormProps) {
  const id = useId()
  const [name, setName] = useState(initial.name)
  const [description, setDescription] = useState(initial.description)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    nameRef.current?.focus()
  }, [])

  function change(nextName: string, nextDescription: string) {
    setName(nextName)
    setDescription(nextDescription)
    setError(null)
    onDirtyChange(nextName !== initial.name || nextDescription !== initial.description)
  }

  async function submit(event: FormEvent) {
    event.preventDefault() // the browser would otherwise reload the page
    if (saving) return
    if (name.trim() === '') {
      setError('כתבו שם לקטגוריה.')
      nameRef.current?.focus()
      return
    }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), description: description.trim() })
    } catch (failure) {
      setError(errorMessage(failure))
      setSaving(false)
      nameRef.current?.focus()
    }
  }

  return (
    <form className="category-form" onSubmit={submit} noValidate>
      <fieldset>
        <legend>{legend}</legend>
        <div className="editor-field">
          <label htmlFor={`${id}-name`} className="field-label">
            שם
          </label>
          <input
            ref={nameRef}
            id={`${id}-name`}
            dir="auto"
            maxLength={MAX_NAME}
            value={name}
            aria-invalid={error !== null}
            aria-describedby={error !== null ? `${id}-error` : undefined}
            onChange={(event) => change(event.target.value, description)}
          />
        </div>
        <div className="editor-field">
          <label htmlFor={`${id}-description`} className="field-label">
            תיאור (המודל מסווג לפיו)
          </label>
          <textarea
            id={`${id}-description`}
            dir="auto"
            rows={3}
            maxLength={MAX_DESCRIPTION}
            value={description}
            aria-describedby={`${id}-count`}
            onChange={(event) => change(name, event.target.value)}
          />
          <p id={`${id}-count`} className="field-hint">
            {description.length} מתוך {MAX_DESCRIPTION} תווים. למשל: מה שייך לכאן, ומה לא.
          </p>
        </div>
        {error !== null && (
          <p id={`${id}-error`} role="alert" className="form-alert">
            {error}
          </p>
        )}
        <div className="button-row">
          <button type="submit" className="button-primary">
            {saving ? 'שומר…' : 'שמירה'}
          </button>
          <button type="button" className="button" onClick={onCancel}>
            ביטול
          </button>
        </div>
      </fieldset>
    </form>
  )
}
