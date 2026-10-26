import type { CategoryRef } from '../types'

interface CategoryChipProps {
  category: CategoryRef | null
  subcategory?: CategoryRef | null
}

// Shows the recipe's category (and subcategory), or "not classified" when it has none. A subcategory
// whose name already starts with its category's ("קינוחים רגילים" under "קינוחים") is shown alone.
export default function CategoryChip({ category, subcategory = null }: CategoryChipProps) {
  if (category === null) {
    return <span className="chip chip-unclassified">לא מסווג</span>
  }
  let label = category.name
  if (subcategory !== null) {
    label = subcategory.name.startsWith(category.name) ? subcategory.name : `${category.name} · ${subcategory.name}`
  }
  return <span className="chip">{label}</span>
}
