import { useId } from 'react'
import Icon from './Icon'

interface TopBarProps {
  /** Which part of the notebook is open, for the navigation's "current page". */
  page: 'recipes' | 'categories' | 'about' | 'other'
  search: string
  onSearch: (text: string) => void
  onHome: () => void
  /** Each of these adds its own button; the public copy has "about" instead of categories and importing. */
  onCategories?: () => void
  onImport?: () => void
  onAbout?: () => void
  /** On a phone: whether the import strip is open (the button opens and closes it). */
  importExpanded?: boolean
}

// Always at the top: the notebook's name (back to the gallery), the search, the navigation, and
// "ייבוא מתכון". On a phone the name shrinks to its logo and the search moves to a second row.
export default function TopBar({ page, search, onSearch, onHome, onCategories, onImport, onAbout, importExpanded }: TopBarProps) {
  const id = useId()
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <h1 className="brand">
          <button type="button" className="brand-button" onClick={onHome}>
            <span className="brand-logo">
              <Icon name="utensils" />
            </span>
            <span className="brand-name">מחברת המתכונים</span>
          </button>
        </h1>
        <search className="topbar-search" aria-label="חיפוש מתכונים">
          <Icon name="search" />
          <label htmlFor={`${id}-search`} className="visually-hidden">
            חיפוש לפי שם מתכון או מצרך
          </label>
          <input id={`${id}-search`} type="search" dir="auto" placeholder="חיפוש מתכון או מצרך" value={search} onChange={(event) => onSearch(event.target.value)} />
        </search>
        <nav className="topbar-nav" aria-label="ניווט ראשי">
          <button type="button" aria-current={page === 'recipes' ? 'page' : undefined} onClick={onHome}>
            מתכונים
          </button>
          {onCategories !== undefined && (
            <button type="button" aria-current={page === 'categories' ? 'page' : undefined} onClick={onCategories}>
              קטגוריות
            </button>
          )}
          {onAbout !== undefined && (
            <button type="button" aria-current={page === 'about' ? 'page' : undefined} onClick={onAbout}>
              על הפרויקט
            </button>
          )}
        </nav>
        {onImport !== undefined && (
          <button
            type="button"
            className="import-button"
            aria-expanded={importExpanded}
            aria-controls={importExpanded === undefined ? undefined : 'quick-import'}
            onClick={onImport}
          >
            <Icon name={importExpanded === true ? 'close' : 'plus'} />
            ייבוא מתכון
          </button>
        )}
      </div>
    </header>
  )
}
