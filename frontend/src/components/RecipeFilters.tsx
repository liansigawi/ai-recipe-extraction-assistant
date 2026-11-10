import { useId, type ReactNode } from 'react'
import { categoryLook, HEALTHY_LABEL } from '../categoryLook'
import { isFiltering, NO_FILTERS, type CategoryFilter, type CookedFilter, type RecipeFilters as Filters, type StatusFilter } from '../recipeFilters'
import type { Category } from '../types'
import Icon from './Icon'

const COOKED: { value: CookedFilter; label: string; icon: 'book' | 'circle' | 'check' }[] = [
  { value: 'all', label: 'הכול', icon: 'book' },
  { value: 'not_yet', label: 'טרם הכנתי', icon: 'circle' },
  { value: 'cooked', label: 'כבר הכנתי', icon: 'check' },
]

const STATUSES: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'הכול' },
  { value: 'saved', label: 'מתכונים' },
  { value: 'draft', label: 'טיוטות' },
]

interface RecipeFiltersProps {
  filters: Filters
  onChange: (filters: Filters) => void
  categories: Category[]
  shown: number
  total: number
  /** How many recipes each "already cooked" choice would show. */
  counts: Record<CookedFilter, number>
  /** The recipes-or-drafts choice; the public copy has no drafts. */
  statusFilter?: boolean
}

/** The top-level category a filter belongs to (its subcategories are then offered). */
function topCategory(categories: Category[], filter: CategoryFilter): Category | undefined {
  if (filter.kind === 'category') return categories.find((c) => c.id === filter.id)
  if (filter.kind === 'subcategory') return categories.find((c) => c.subcategories.some((s) => s.id === filter.id))
  return undefined
}

// The filters above the gallery: "already cooked" first (with counts), the categories (their drawings
// and colors as on the cards), the subcategories of the chosen one, and drafts. Radio buttons, shown as
// chips; the real inputs stay for the keyboard. The search box is in the top bar. App filters the list.
export default function RecipeFilters({ filters, onChange, categories, shown, total, counts, statusFilter = true }: RecipeFiltersProps) {
  const id = useId()
  const top = topCategory(categories, filters.category)
  // The healthy-style filter belongs to the desserts: choosing another category turns it off.
  const setCategory = (category: CategoryFilter) =>
    onChange({ ...filters, category, healthy: filters.healthy && topCategory(categories, category)?.healthy_style === true })

  return (
    <search className="recipe-filters" aria-label="סינון מתכונים">
      <fieldset className="cooked-filter">
        <legend className="visually-hidden">מה כבר הכנתי</legend>
        {COOKED.map((option) => (
          <label key={option.value} className={`cooked-option cooked-option-${option.value}`}>
            <input
              type="radio"
              name={`${id}-cooked`}
              checked={filters.cooked === option.value}
              onChange={() => onChange({ ...filters, cooked: option.value })}
            />
            <span>
              <Icon name={option.icon} />
              {option.label}{' '}
              {/* The space keeps "טרם הכנתי 4" two words for screen readers; on screen the gap spaces them. */}
              <span className="filter-count">{counts[option.value]}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div className="filter-rows">
        <fieldset className="category-filter">
          <legend className="visually-hidden">קטגוריה</legend>
          <div className="chip-row">
            <Chip name={`${id}-category`} checked={filters.category.kind === 'all'} onPick={() => setCategory({ kind: 'all' })}>
              הכול
            </Chip>
            {categories.map((category) => {
              const look = categoryLook(category)
              return (
                <Chip key={category.id} name={`${id}-category`} checked={top?.id === category.id} onPick={() => setCategory({ kind: 'category', id: category.id })}>
                  <span className={`chip-icon tone-${look.tone}`}>
                    <Icon name={look.icon} />
                  </span>
                  {category.name}
                </Chip>
              )
            })}
            <Chip name={`${id}-category`} checked={filters.category.kind === 'unclassified'} onPick={() => setCategory({ kind: 'unclassified' })}>
              <span className="chip-icon tone-none">
                <Icon name="book" />
              </span>
              לא מסווג
            </Chip>
          </div>
        </fieldset>

        {statusFilter && (
          <fieldset className="status-filter">
            <legend className="visually-hidden">מתכונים וטיוטות</legend>
            {STATUSES.map((status) => (
              <Chip key={status.value} name={`${id}-status`} small checked={filters.status === status.value} onPick={() => onChange({ ...filters, status: status.value })}>
                {status.label}
              </Chip>
            ))}
          </fieldset>
        )}
      </div>

      {top !== undefined && (top.subcategories.length > 0 || top.healthy_style === true) && (
        <fieldset className="subcategory-filter">
          <legend>{top.name}:</legend>
          <Chip name={`${id}-sub`} small checked={filters.category.kind === 'category'} onPick={() => setCategory({ kind: 'category', id: top.id })}>
            {`כל ה${top.name}`}
          </Chip>
          {top.subcategories.map((sub) => (
            <Chip
              key={sub.id}
              name={`${id}-sub`}
              small
              checked={filters.category.kind === 'subcategory' && filters.category.id === sub.id}
              onPick={() => setCategory({ kind: 'subcategory', id: sub.id })}
            >
              {sub.name}
            </Chip>
          ))}
          {top.healthy_style === true && (
            <label className="filter-chip is-small is-toggle">
              <input type="checkbox" checked={filters.healthy} onChange={(event) => onChange({ ...filters, healthy: event.target.checked })} />
              <span>
                <Icon name="leaf" />
                {HEALTHY_LABEL}
              </span>
            </label>
          )}
        </fieldset>
      )}

      <p className="filter-summary" aria-live="polite">
        {isFiltering(filters) ? `${shown} מתוך ${total} מתכונים` : `${total} מתכונים`}
        {isFiltering(filters) && (
          <button type="button" className="text-button" onClick={() => onChange(NO_FILTERS)}>
            ניקוי
          </button>
        )}
      </p>
    </search>
  )
}

function Chip({ name, checked, onPick, small = false, children }: { name: string; checked: boolean; onPick: () => void; small?: boolean; children: ReactNode }) {
  return (
    <label className={small ? 'filter-chip is-small' : 'filter-chip'}>
      <input type="radio" name={name} checked={checked} onChange={onPick} />
      <span>{children}</span>
    </label>
  )
}
