import type { CategoryRef } from '../types'

interface CategoryChipProps {
  category: CategoryRef | null
  subcategory?: CategoryRef | null // optional prop: the card leaves it out, the recipe view passes it
}

// Shows the recipe's category, or "not classified" when it has none.
export default function CategoryChip({ category, subcategory = null }: CategoryChipProps) {
  if (category === null) {
    return <span className="chip chip-unclassified">לא מסווג</span>
  }
  return (
    <span className="chip">
      {category.name}
      {subcategory !== null && ` · ${subcategory.name}`}
    </span>
  )
}
