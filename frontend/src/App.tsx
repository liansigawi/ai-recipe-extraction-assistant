import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError, deleteRecipe, errorMessage, listCategories, listRecipes } from './api'
import CategoryManager from './components/CategoryManager'
import ImportPanel from './components/ImportPanel'
import RecipeActions from './components/RecipeActions'
import RecipeEditor from './components/RecipeEditor'
import RecipeFilters from './components/RecipeFilters'
import RecipeList from './components/RecipeList'
import RecipeView from './components/RecipeView'
import { filterRecipes, isFiltering, NO_FILTERS, type RecipeFilters as Filters } from './recipeFilters'
import type { Category, Recipe } from './types'

// What the main area shows. A "discriminated union": `kind` tells which shape the value has,
// and TypeScript allows `recipeId` only where kind is 'edit'.
type Mode =
  | { kind: 'view' }
  | { kind: 'edit'; recipeId: number }
  | { kind: 'create' }
  | { kind: 'import' }
  | { kind: 'categories' }
type Loading = { status: 'loading' } | { status: 'failed'; message: string } | { status: 'ready' }

const DISCARD_QUESTION = 'לצאת מהעריכה? השינויים שלא נשמרו יאבדו.'

// App owns the notebook's data and decides what is shown. The list, the recipe view and
// the editor get what they need as props, and report back through function props.
export default function App() {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState<Loading>({ status: 'loading' })
  const [loadAttempt, setLoadAttempt] = useState(0) // changing it loads everything again
  // null means "the user has not chosen yet".
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [mode, setMode] = useState<Mode>({ kind: 'view' })
  const [unsavedChanges, setUnsavedChanges] = useState(false)
  const [notice, setNotice] = useState('') // "saved" / "deleted" confirmations
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)

  // Derived on every render instead of stored: the recipes the search and filters let through, and
  // the chosen recipe, or until the user chooses (or if the chosen one is gone) the first one shown.
  // undefined only for an empty notebook.
  const shown = filterRecipes(recipes, filters)
  const selected = recipes.find((recipe) => recipe.id === selectedId) ?? shown.at(0) ?? recipes.at(0)
  const editing = mode.kind === 'edit' ? recipes.find((recipe) => recipe.id === mode.recipeId) : undefined

  // useRef keeps a reference to the recipe title element on the page.
  const titleRef = useRef<HTMLHeadingElement>(null)
  // A ref can also hold a plain value that survives re-renders without causing one.
  const focusTitleAfterRender = useRef(false)
  // What the page showed at the latest render, for code that runs later, such as an import that
  // finishes after the user has moved on. (A ref is updated in an effect, not while rendering.)
  const latest = useRef({ mode, shownId: selected?.id ?? null })
  useEffect(() => {
    latest.current = { mode, shownId: selected?.id ?? null }
  })

  // Load the notebook from the API when the page opens, and again after "Try again".
  useEffect(() => {
    // Set when this request's answer is no longer wanted (a newer attempt started, or React's
    // development-only practice run in StrictMode), so a late answer cannot overwrite a newer one.
    let ignore = false
    // Promise.all: both requests run at the same time; continue when both have answered.
    Promise.all([listRecipes(), listCategories()]).then(
      ([loadedRecipes, loadedCategories]) => {
        if (ignore) return
        setRecipes(loadedRecipes)
        setCategories(loadedCategories)
        setLoading({ status: 'ready' })
      },
      (error: unknown) => {
        if (!ignore) setLoading({ status: 'failed', message: errorMessage(error) })
      },
    )
    // The cleanup function: React calls it before running this effect again, and when App goes away.
    return () => {
      ignore = true
    }
  }, [loadAttempt])

  // While the editor has unsaved changes, closing or reloading the tab asks first.
  useEffect(() => {
    if (!unsavedChanges) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsavedChanges])

  // After the user picks a recipe, bring its title into view if it is off-screen (on narrow
  // screens the recipe is below the list). Keyboard focus stays on the chosen card.
  useEffect(() => {
    const title = titleRef.current
    if (selectedId === null || title === null) return
    const box = title.getBoundingClientRect()
    if (box.top < 0 || box.bottom > window.innerHeight) {
      title.scrollIntoView({ block: 'start' })
    }
  }, [selectedId])

  // No dependency list: runs after every render. Saving, cancelling and deleting remove the
  // button that had keyboard focus, so they ask for focus to move to the title now shown.
  useEffect(() => {
    if (!focusTitleAfterRender.current) return
    focusTitleAfterRender.current = false
    titleRef.current?.focus()
  })

  /** Closes the editor, asking first if that would lose changes. false: the user chose to stay. */
  function closeEditor(): boolean {
    if (mode.kind !== 'view' && unsavedChanges && !window.confirm(DISCARD_QUESTION)) return false
    setMode({ kind: 'view' })
    setUnsavedChanges(false)
    return true
  }

  function handleSelect(id: number) {
    if (!closeEditor()) return
    setSelectedId(id)
    setNotice('')
  }

  function handleCreate() {
    if (!closeEditor()) return
    setMode({ kind: 'create' })
    setNotice('')
  }

  function handleImport() {
    if (!closeEditor()) return
    setMode({ kind: 'import' })
    setNotice('')
  }

  function handleManageCategories() {
    if (!closeEditor()) return
    setMode({ kind: 'categories' })
    setNotice('')
  }

  /** After a category was created or changed: the categories, and the recipes' category names, again. */
  async function reloadAfterCategoryChange() {
    const [loadedRecipes, loadedCategories] = await Promise.all([listRecipes(), listCategories()])
    setRecipes(loadedRecipes)
    setCategories(loadedCategories)
  }

  function handleImported(draft: Recipe) {
    setRecipes((current) => [draft, ...current])
    if (latest.current.mode.kind === 'import') {
      // Straight on to the review: the draft opens in the editor, beside its original text.
      setSelectedId(draft.id)
      setMode({ kind: 'edit', recipeId: draft.id })
      setNotice('הטיוטה מוכנה: השוו אותה לטקסט המקורי, תקנו, ושמרו.')
    } else {
      // The user went elsewhere while Claude was reading: do not pull them away. Until they pick
      // a recipe the page shows the first one, which would now be the draft, so pin the one shown.
      const shownId = latest.current.shownId
      setSelectedId((current) => current ?? shownId)
      setNotice(`הטיוטה "${draft.title}" מוכנה לבדיקה ברשימה.`)
    }
  }

  /** A recipe changed outside the editor (its pictures and videos): the new copy replaces the old one. */
  function handleRecipeChanged(changed: Recipe) {
    setRecipes((current) => current.map((recipe) => (recipe.id === changed.id ? changed : recipe)))
  }

  function handleEdit(id: number) {
    setMode({ kind: 'edit', recipeId: id })
    setNotice('')
  }

  function handleCancel() {
    if (closeEditor()) focusTitleAfterRender.current = true
  }

  function handleSaved(saved: Recipe) {
    // An updater function receives the latest list. Replace the old copy, or put a new recipe
    // first: the list is newest first, as the API sends it.
    setRecipes((current) =>
      current.some((recipe) => recipe.id === saved.id)
        ? current.map((recipe) => (recipe.id === saved.id ? saved : recipe))
        : [saved, ...current],
    )
    setSelectedId(saved.id)
    setMode({ kind: 'view' })
    setUnsavedChanges(false)
    setNotice(saved.status === 'draft' ? 'הטיוטה נשמרה. אפשר להמשיך לבדוק אותה אחר כך.' : 'המתכון נשמר.')
    focusTitleAfterRender.current = true
  }

  async function handleDelete(id: number) {
    try {
      await deleteRecipe(id)
    } catch (error) {
      // Already gone, e.g. deleted in another tab: the goal is reached, so carry on.
      // Any other failure goes back to RecipeActions, which shows it.
      if (!(error instanceof ApiError && error.code === 'recipe_not_found')) throw error
    }
    setRecipes((current) => current.filter((recipe) => recipe.id !== id))
    setSelectedId(null) // show the first recipe
    setNotice('המתכון נמחק.')
    focusTitleAfterRender.current = true
  }

  function handleRetry() {
    setLoading({ status: 'loading' })
    setLoadAttempt((attempt) => attempt + 1)
  }

  let content: ReactNode
  if (mode.kind === 'import') {
    content = <ImportPanel onImported={handleImported} onCancel={handleCancel} onOpenRecipe={handleSelect} />
  } else if (mode.kind === 'categories') {
    content = (
      <CategoryManager
        categories={categories}
        recipes={recipes}
        onChanged={reloadAfterCategoryChange}
        onClose={handleCancel}
        onDirtyChange={setUnsavedChanges}
      />
    )
  } else if (mode.kind === 'create') {
    // A different key gives a fresh editor with fresh state, instead of reusing the previous one.
    content = (
      <RecipeEditor
        key="new"
        categories={categories}
        onSaved={handleSaved}
        onCancel={handleCancel}
        onDirtyChange={setUnsavedChanges}
      />
    )
  } else if (editing !== undefined) {
    content = (
      <RecipeEditor
        key={editing.id}
        recipe={editing}
        categories={categories}
        onSaved={handleSaved}
        onCancel={handleCancel}
        onDirtyChange={setUnsavedChanges}
      />
    )
  } else if (selected !== undefined) {
    content = (
      <RecipeView
        recipe={selected}
        titleRef={titleRef}
        onChange={handleRecipeChanged}
        // key: a new recipe gets fresh buttons, so a delete question left open does not carry over.
        actions={
          <RecipeActions
            key={selected.id}
            editLabel={selected.status === 'draft' ? 'בדיקה ושמירה' : 'עריכה'}
            onEdit={() => handleEdit(selected.id)}
            onDelete={() => handleDelete(selected.id)}
          />
        }
      />
    )
  } else {
    content = <p className="empty-state">אין מתכון להצגה. אפשר להוסיף אחד בכפתור "מתכון חדש".</p>
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">מחברת המתכונים</h1>
        {/* <output> is a "status" region: a screen reader announces text that appears in it.
            It stays in the page even when empty, so the announcement is not missed. */}
        <output className="notice">{notice}</output>
      </header>

      {loading.status === 'loading' && <p className="empty-state">טוען את המתכונים…</p>}

      {loading.status === 'failed' && (
        <div role="alert" className="load-error">
          <p>לא הצלחנו לטעון את המחברת. {loading.message}</p>
          <button type="button" className="button" onClick={handleRetry}>
            נסו שוב
          </button>
        </div>
      )}

      {loading.status === 'ready' && (
        <div className="app-body">
          <nav aria-labelledby="recipe-list-heading">
            <div className="list-header">
              <h2 id="recipe-list-heading" className="list-heading">
                מתכונים
              </h2>
              <div className="button-row">
                <button type="button" className="button-primary" onClick={handleImport}>
                  ייבוא מתכון
                </button>
                <button type="button" className="button" onClick={handleCreate}>
                  מתכון חדש
                </button>
                <button type="button" className="button" aria-pressed={mode.kind === 'categories'} onClick={handleManageCategories}>
                  קטגוריות
                </button>
              </div>
            </div>
            {recipes.length > 0 && (
              <RecipeFilters filters={filters} onChange={setFilters} categories={categories} shown={shown.length} total={recipes.length} />
            )}
            <RecipeList
              recipes={shown}
              selectedId={mode.kind === 'view' || mode.kind === 'edit' ? (editing ?? selected)?.id ?? null : null}
              onSelect={handleSelect}
              onClearFilters={isFiltering(filters) ? () => setFilters(NO_FILTERS) : undefined}
            />
          </nav>

          <main>{content}</main>
        </div>
      )}
    </div>
  )
}
