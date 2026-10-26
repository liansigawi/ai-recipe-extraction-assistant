import { useId } from 'react'
import { categoryFilterFrom, categoryFilterValue, isFiltering, NO_FILTERS, type RecipeFilters as Filters, type StatusFilter } from '../recipeFilters'
import type { Category } from '../types'

const STATUSES: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'הכל' },
  { value: 'saved', label: 'מתכונים' },
  { value: 'draft', label: 'טיוטות' },
]

interface RecipeFiltersProps {
  filters: Filters
  onChange: (filters: Filters) => void
  categories: Category[]
  shown: number
  total: number
}

// The search box and the filters above the recipe list. The list itself is filtered by App (with
// filterRecipes), so this component only shows the choices and reports changes.
export default function RecipeFilters({ filters, onChange, categories, shown, total }: RecipeFiltersProps) {
  const id = useId()
  const filtering = isFiltering(filters)

  return (
    <search className="recipe-filters" aria-label="חיפוש וסינון מתכונים">
      <label htmlFor={`${id}-text`} className="visually-hidden">
        חיפוש לפי שם מתכון או מצרך
      </label>
      <input
        id={`${id}-text`}
        type="search"
        dir="auto"
        className="filter-search"
        placeholder="חיפוש לפי שם או מצרך"
        value={filters.text}
        onChange={(event) => onChange({ ...filters, text: event.target.value })}
      />
      <div className="filter-row">
        <label htmlFor={`${id}-category`} className="visually-hidden">
          סינון לפי קטגוריה
        </label>
        <select
          id={`${id}-category`}
          className="filter-category"
          value={categoryFilterValue(filters.category)}
          onChange={(event) => onChange({ ...filters, category: categoryFilterFrom(event.target.value) })}
        >
          <option value="all">כל הקטגוריות</option>
          <option value="none">לא מסווג</option>
          {categories.map((category) => [
            <option key={`c${category.id}`} value={`c:${category.id}`}>
              {category.name}
            </option>,
            ...category.subcategories.map((sub) => (
              <option key={`s${sub.id}`} value={`s:${sub.id}`}>
                {'\u00a0\u00a0\u00a0'}↳ {sub.name}
              </option>
            )),
          ])}
        </select>
        <fieldset className="status-filter">
          <legend className="visually-hidden">אילו מתכונים להציג</legend>
          {STATUSES.map((status) => (
            <label key={status.value} className={filters.status === status.value ? 'status-option status-option-on' : 'status-option'}>
              <input
                type="radio"
                name={`${id}-status`}
                value={status.value}
                checked={filters.status === status.value}
                onChange={() => onChange({ ...filters, status: status.value })}
              />
              {status.label}
            </label>
          ))}
        </fieldset>
      </div>
      <p className="filter-summary" aria-live="polite">
        {filtering ? `${shown} מתוך ${total} מתכונים` : `${total} מתכונים`}
        {filtering && (
          <button type="button" className="text-button" onClick={() => onChange(NO_FILTERS)}>
            ניקוי
          </button>
        )}
      </p>
    </search>
  )
}
