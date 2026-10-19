import { useEffect, useRef, useState } from 'react'
import RecipeList from './components/RecipeList'
import RecipeView from './components/RecipeView'
import type { Recipe } from './types'

interface AppProps {
  recipes: Recipe[]
}

// The selected recipe is needed by two components: the list (to highlight a card) and the
// view (to show it). So the state lives here, in their common parent, and flows down as props.
export default function App({ recipes }: AppProps) {
  // useState returns the current value and a function that changes it and re-renders App.
  // null means "the user has not chosen yet".
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Derived on every render instead of stored: the chosen recipe, or the first one until the
  // user chooses (or if the chosen one is no longer in the list). undefined only for an empty list.
  const selected = recipes.find((recipe) => recipe.id === selectedId) ?? recipes.at(0)

  // useRef keeps a reference to the recipe title element on the page.
  const titleRef = useRef<HTMLHeadingElement>(null)

  // useEffect runs after React has updated the page. After the user picks a recipe, bring its
  // title into view if it is off-screen (on narrow screens the recipe is below the list).
  // Keyboard focus stays on the chosen card, like a tab that switches the panel beside it.
  useEffect(() => {
    const title = titleRef.current
    if (selectedId === null || title === null) return
    const box = title.getBoundingClientRect()
    if (box.top < 0 || box.bottom > window.innerHeight) {
      title.scrollIntoView({ block: 'start' })
    }
  }, [selectedId])

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">מחברת המתכונים</h1>
        <p className="sample-banner">מתכוני דוגמה בלבד: המחברת עדיין לא שומרת ולא טוענת מתכונים.</p>
      </header>

      <div className="app-body">
        <nav aria-labelledby="recipe-list-heading">
          <h2 id="recipe-list-heading" className="list-heading">
            מתכונים
          </h2>
          <RecipeList recipes={recipes} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
        </nav>

        <main>
          {selected !== undefined ? (
            <RecipeView recipe={selected} titleRef={titleRef} />
          ) : (
            <p className="empty-state">אין מתכון להצגה.</p>
          )}
        </main>
      </div>
    </div>
  )
}
