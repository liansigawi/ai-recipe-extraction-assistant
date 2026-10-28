import { categoryLabel } from '../categoryLook'
import type { CategoryRef } from '../types'

interface CategoryChipProps {
  category: CategoryRef | null
  subcategory?: CategoryRef | null
}

// Shows the recipe's category (and subcategory), or "not classified" when it has none. A subcategory
// whose name already starts with its category's ("קינוחים רגילים" under "קינוחים") is shown alone.
export default function CategoryChip({ category, subcategory = null }: CategoryChipProps) {
  return <span className={category === null ? 'chip chip-unclassified' : 'chip'}>{categoryLabel(category, subcategory)}</span>
}
