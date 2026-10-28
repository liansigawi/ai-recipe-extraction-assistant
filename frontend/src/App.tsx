import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError, deleteRecipe, errorMessage, listCategories, listRecipes, setCooked } from './api'
import CategoryManager from './components/CategoryManager'
import { CookedControl } from './components/CookedControl'
import GalleryNotice, { type GalleryMessage } from './components/GalleryNotice'
import Icon from './components/Icon'
import ImportPanel from './components/ImportPanel'
import QuickImport from './components/QuickImport'
import RecipeActions from './components/RecipeActions'
import RecipeEditor from './components/RecipeEditor'
import RecipeFilters from './components/RecipeFilters'
import RecipeList from './components/RecipeList'
import RecipeView from './components/RecipeView'
import TopBar from './components/TopBar'
import { cookedCounts, filterRecipes, isFiltering, NO_FILTERS, type RecipeFilters as Filters } from './recipeFilters'
import { hashOf, routeFromHash, type Route } from './route'
import type { Category, Recipe } from './types'
import { useNarrowScreen } from './useNarrowScreen'

type Loading = { status: 'loading' } | { status: 'failed'; message: string } | { status: 'ready' }

const DISCARD_QUESTION = 'לצאת מהעריכה? השינויים שלא נשמרו יאבדו.'
const IMPORT_STRIP = 'quick-import'

// App owns the notebook's data and decides what is shown: the gallery ("home"), one recipe, the
// editor, the import screen or the categories. Where the page is (the route) is also kept in the
// address after "#", so the browser's back button and a reload work (route.ts).
export default function App() {
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState<Loading>({ status: 'loading' })
  const [loadAttempt, setLoadAttempt] = useState(0) // changing it loads everything again
  // A function given to useState runs once: start where the address says.
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash))
  const [unsavedChanges, setUnsavedChanges] = useState(false)
  const [notice, setNotice] = useState('') // "saved" / "deleted" confirmations
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const narrow = useNarrowScreen()
  const [importOpen, setImportOpen] = useState(false) // phones: the import strip opens from the top bar
  // The gallery's badges: the marks being saved (a second click waits), and the note after a change.
  const [savingCooked, setSavingCooked] = useState<ReadonlySet<number>>(new Set())
  const [galleryMessage, setGalleryMessage] = useState<GalleryMessage | null>(null)
  const [undoing, setUndoing] = useState(false)

  // Derived on every render instead of stored.
  const shown = filterRecipes(recipes, filters)
  const viewing = route.kind === 'view' ? recipes.find((recipe) => recipe.id === route.recipeId) : undefined
  const editing = route.kind === 'edit' ? recipes.find((recipe) => recipe.id === route.recipeId) : undefined
  // A recipe the address names but the notebook does not have (deleted, or a typo): the gallery.
  const missing = loading.status === 'ready' && ((route.kind === 'view' && viewing === undefined) || (route.kind === 'edit' && editing === undefined))
  const page: Route = missing ? { kind: 'home' } : route
  const viewedId = page.kind === 'view' ? page.recipeId : null

  // useRef keeps a reference to an element on the page, or a value that survives re-renders.
  const titleRef = useRef<HTMLHeadingElement>(null)
  const galleryHeadingRef = useRef<HTMLHeadingElement>(null)
  const importInputRef = useRef<HTMLInputElement>(null)
  const focusAfterRender = useRef<'title' | 'gallery' | 'import' | 'undo' | 'badge' | null>(null)
  const undoRef = useRef<HTMLButtonElement>(null)
  const badgeToFocus = useRef<number | null>(null) // after "ביטול": the badge of the recipe that came back
  const galleryScroll = useRef(0) // where the gallery was scrolled to, for coming back to it
  const lastOpened = useRef<number | null>(null) // the recipe opened from the gallery, to focus its card again
  // What the page showed at the latest render, for code that runs later: an import that finishes
  // after the user moved on, or the browser's back button. (A ref is updated in an effect.)
  const latest = useRef({ route: page, unsavedChanges, filters })
  useEffect(() => {
    latest.current = { route: page, unsavedChanges, filters }
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

  // The browser's back and forward buttons: show where the address now points, asking first if that
  // would lose the editor's changes (if the user stays, the address is put back).
  useEffect(() => {
    function onPopState() {
      const next = routeFromHash(window.location.hash)
      if (latest.current.unsavedChanges && !window.confirm(DISCARD_QUESTION)) {
        window.history.pushState(null, '', hashOf(latest.current.route) || window.location.pathname)
        return
      }
      setUnsavedChanges(false)
      arrive(latest.current.route, next)
      setRoute(next)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // ...and the address says so too.
  useEffect(() => {
    if (missing) window.history.replaceState(null, '', window.location.pathname)
  }, [missing])

  // After the page changed: the gallery comes back where it was scrolled to; anything else starts at the top.
  useLayoutEffect(() => {
    window.scrollTo(0, page.kind === 'home' ? galleryScroll.current : 0)
  }, [page.kind, viewedId])

  // No dependency list: runs after every render. Moving between pages removes the button that had
  // keyboard focus, so focus goes to what was asked for: the recipe's title, the card the user came
  // back from, the gallery, or the import strip's link field.
  useEffect(() => {
    const target = focusAfterRender.current
    if (target === null) return
    focusAfterRender.current = null
    if (target === 'title') titleRef.current?.focus()
    if (target === 'import') importInputRef.current?.focus()
    if (target === 'undo') undoRef.current?.focus()
    if (target === 'gallery') {
      const card = document.querySelector<HTMLElement>(`[data-recipe-id="${lastOpened.current}"] .recipe-card-open`)
      ;(card ?? galleryHeadingRef.current)?.focus()
    }
    if (target === 'badge') {
      const badge = document.querySelector<HTMLElement>(`[data-recipe-id="${badgeToFocus.current}"] .cooked-badge`)
      ;(badge ?? galleryHeadingRef.current)?.focus()
    }
  })

  /** Remember what leaving `from` for `to` needs: the gallery's scroll, and where focus goes. */
  function arrive(from: Route, to: Route) {
    if (from.kind === 'home' && to.kind !== 'home') galleryScroll.current = window.scrollY
    if (to.kind === 'view') {
      lastOpened.current = to.recipeId
      focusAfterRender.current = 'title'
    }
    if (to.kind === 'home' && from.kind !== 'home') focusAfterRender.current = 'gallery'
  }

  /** Go to another page, asking first if that would lose the editor's changes. false: the user stayed. */
  function go(next: Route, { replace = false } = {}): boolean {
    if (page.kind !== 'home' && page.kind !== 'view' && unsavedChanges && !window.confirm(DISCARD_QUESTION)) return false
    setUnsavedChanges(false)
    arrive(page, next)
    setRoute(next)
    setNotice('')
    setGalleryMessage(null)
    if (next.kind !== 'home') setImportOpen(false)
    const address = hashOf(next) || window.location.pathname
    if (replace) window.history.replaceState(null, '', address)
    else if (hashOf(next) !== window.location.hash) window.history.pushState(null, '', address)
    return true
  }

  const goHome = () => go({ kind: 'home' })
  const openRecipe = (id: number) => go({ kind: 'view', recipeId: id })

  /** "ייבוא מתכון" in the top bar: on a phone it opens and closes the import strip; on a wider screen
   * the strip is always there and the button moves focus to its link field. */
  function handleImportButton() {
    if (page.kind !== 'home') {
      if (!go({ kind: 'home' })) return
      setImportOpen(true)
      focusAfterRender.current = 'import'
      return
    }
    if (narrow) {
      if (!importOpen) focusAfterRender.current = 'import'
      setImportOpen(!importOpen)
    } else {
      importInputRef.current?.focus()
    }
  }

  /** Typing a search shows the gallery, wherever the page was; the typing goes on in the search box. */
  function handleSearch(text: string) {
    if (page.kind !== 'home') {
      if (!go({ kind: 'home' })) return
      focusAfterRender.current = null
    }
    setFilters((current) => ({ ...current, text }))
  }

  /** After a category was created or changed: the categories, and the recipes' category names, again. */
  async function reloadAfterCategoryChange() {
    const [loadedRecipes, loadedCategories] = await Promise.all([listRecipes(), listCategories()])
    setRecipes(loadedRecipes)
    setCategories(loadedCategories)
  }

  function handleImported(draft: Recipe) {
    setRecipes((current) => [draft, ...current])
    if (latest.current.route.kind === 'import') {
      // Straight on to the review: the draft opens in the editor, beside its original text.
      go({ kind: 'edit', recipeId: draft.id }, { replace: true })
      setNotice('הטיוטה מוכנה: השוו אותה לטקסט המקורי, תקנו, ושמרו.')
    } else {
      // The user went elsewhere while the model was reading: do not pull them away.
      setNotice(`הטיוטה "${draft.title}" מוכנה לבדיקה ברשימה.`)
    }
  }

  /** A recipe changed outside the editor (its media, its cooked mark): the new copy replaces the old one. */
  function handleRecipeChanged(changed: Recipe) {
    setRecipes((current) => current.map((recipe) => (recipe.id === changed.id ? changed : recipe)))
  }

  /** A card's badge: save the opposite mark. The card shows what was saved, never a guess: if saving
   * fails it stays as it was, with a message. If the filters now hide the card, a note offers "ביטול". */
  async function handleToggleCooked(recipe: Recipe) {
    if (savingCooked.has(recipe.id)) return
    setSavingCooked((current) => new Set(current).add(recipe.id))
    setGalleryMessage(null)
    try {
      const saved = await setCooked(recipe.id, !recipe.cooked)
      handleRecipeChanged(saved)
      if (filterRecipes([saved], latest.current.filters).length === 0) {
        setGalleryMessage({ kind: 'hidden', recipe: saved, previous: recipe.cooked })
        focusAfterRender.current = 'undo' // the badge that had the focus is gone with its card
      }
    } catch (failure) {
      setGalleryMessage({ kind: 'error', title: recipe.title, text: errorMessage(failure) })
    } finally {
      setSavingCooked((current) => {
        const next = new Set(current)
        next.delete(recipe.id)
        return next
      })
    }
  }

  /** "ביטול" in the note: the mark goes back, and so does the card (with the focus on its badge). */
  async function handleUndoCooked() {
    if (galleryMessage?.kind !== 'hidden' || undoing) return
    const { recipe, previous } = galleryMessage
    setUndoing(true)
    try {
      handleRecipeChanged(await setCooked(recipe.id, previous))
      setGalleryMessage(null)
      badgeToFocus.current = recipe.id
      focusAfterRender.current = 'badge'
    } catch (failure) {
      setGalleryMessage({ kind: 'error', title: recipe.title, text: errorMessage(failure) })
    } finally {
      setUndoing(false)
    }
  }

  function handleCancel() {
    // Back where the user came from: the recipe being edited, or the gallery.
    const back: Route = page.kind === 'edit' ? { kind: 'view', recipeId: page.recipeId } : { kind: 'home' }
    if (go(back, { replace: page.kind === 'edit' })) focusAfterRender.current = back.kind === 'view' ? 'title' : 'gallery'
  }

  function handleSaved(saved: Recipe) {
    // An updater function receives the latest list. Replace the old copy, or put a new recipe
    // first: the list is newest first, as the API sends it.
    setRecipes((current) =>
      current.some((recipe) => recipe.id === saved.id)
        ? current.map((recipe) => (recipe.id === saved.id ? saved : recipe))
        : [saved, ...current],
    )
    setUnsavedChanges(false)
    arrive(page, { kind: 'view', recipeId: saved.id })
    setRoute({ kind: 'view', recipeId: saved.id })
    window.history.replaceState(null, '', hashOf({ kind: 'view', recipeId: saved.id }))
    setNotice(saved.status === 'draft' ? 'הטיוטה נשמרה. אפשר להמשיך לבדוק אותה אחר כך.' : 'המתכון נשמר.')
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
    lastOpened.current = null // its card is gone: focus goes to the gallery itself
    go({ kind: 'home' }, { replace: true })
    setNotice('המתכון נמחק.')
  }

  function handleRetry() {
    setLoading({ status: 'loading' })
    setLoadAttempt((attempt) => attempt + 1)
  }

  let content: ReactNode
  if (page.kind === 'import') {
    content = (
      <ImportPanel
        onImported={handleImported}
        onCancel={handleCancel}
        onOpenRecipe={openRecipe}
        initialUrl={page.url}
        startNow={page.start}
        focusText={page.focusText}
      />
    )
  } else if (page.kind === 'categories') {
    content = (
      <CategoryManager
        categories={categories}
        recipes={recipes}
        onChanged={reloadAfterCategoryChange}
        onClose={handleCancel}
        onDirtyChange={setUnsavedChanges}
      />
    )
  } else if (page.kind === 'create') {
    content = <RecipeEditor key="new" categories={categories} onSaved={handleSaved} onCancel={handleCancel} onDirtyChange={setUnsavedChanges} />
  } else if (editing !== undefined) {
    // A different key gives a fresh editor with fresh state, instead of reusing the previous one.
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
  } else if (viewing !== undefined) {
    content = (
      <RecipeView
        recipe={viewing}
        titleRef={titleRef}
        onChange={handleRecipeChanged}
        toolbar={
          <div className="page-toolbar">
            <button type="button" className="back-button" onClick={goHome}>
              <Icon name="back" />
              כל המתכונים
            </button>
            {/* key: a new recipe gets fresh buttons, so a delete question left open does not carry over. */}
            <RecipeActions
              key={viewing.id}
              editLabel={viewing.status === 'draft' ? 'בדיקה ושמירה' : 'עריכה'}
              onEdit={() => go({ kind: 'edit', recipeId: viewing.id })}
              onDelete={() => handleDelete(viewing.id)}
            />
          </div>
        }
        cooked={<CookedControl key={viewing.id} recipe={viewing} onChange={handleRecipeChanged} />}
      />
    )
  } else {
    const filtering = isFiltering(filters)
    content = (
      <>
        {(!narrow || importOpen) && (
          <QuickImport
            id={IMPORT_STRIP}
            inputRef={importInputRef}
            onImportLink={(url) => go({ kind: 'import', url, start: true })}
            onPasteText={() => go({ kind: 'import', focusText: true })}
            onCreate={() => go({ kind: 'create' })}
          />
        )}
        {recipes.length > 0 && (
          <RecipeFilters
            filters={filters}
            onChange={setFilters}
            categories={categories}
            shown={shown.length}
            total={recipes.length}
            counts={cookedCounts(recipes, filters)}
          />
        )}
        <RecipeList
          recipes={shown}
          onOpen={openRecipe}
          onToggleCooked={handleToggleCooked}
          savingCooked={savingCooked}
          onClearFilters={filtering ? () => setFilters(NO_FILTERS) : undefined}
          headingRef={galleryHeadingRef}
        />
        <GalleryNotice
          message={galleryMessage}
          onUndo={handleUndoCooked}
          onClose={() => setGalleryMessage(null)}
          undoRef={undoRef}
          undoing={undoing}
        />
      </>
    )
  }

  return (
    <div className="app">
      <TopBar
        page={page.kind === 'categories' ? 'categories' : page.kind === 'home' || page.kind === 'view' ? 'recipes' : 'other'}
        search={filters.text}
        onSearch={handleSearch}
        onHome={goHome}
        onCategories={() => go({ kind: 'categories' })}
        onImport={handleImportButton}
        importExpanded={narrow && page.kind === 'home' ? importOpen : undefined}
      />

      <div className="app-content">
        {/* <output> is a "status" region: a screen reader announces text that appears in it.
            It stays in the page even when empty, so the announcement is not missed. */}
        <output className="notice">{notice}</output>

        {loading.status === 'loading' && <p className="empty-state">טוען את המתכונים…</p>}

        {loading.status === 'failed' && (
          <div role="alert" className="load-error">
            <p>לא הצלחנו לטעון את המחברת. {loading.message}</p>
            <button type="button" className="button" onClick={handleRetry}>
              נסו שוב
            </button>
          </div>
        )}

        {loading.status === 'ready' && <main className={`page page-${page.kind}`}>{content}</main>}
      </div>
    </div>
  )
}
