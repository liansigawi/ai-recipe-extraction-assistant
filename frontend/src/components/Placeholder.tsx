import { categoryLook } from '../categoryLook'
import type { CategoryRef } from '../types'
import Icon from './Icon'

/** A recipe without a picture: its category's drawing on its category's color. Decorative. */
export default function Placeholder({ category }: { category: CategoryRef | null }) {
  const look = categoryLook(category)
  return (
    <span className={`placeholder tone-${look.tone}`} aria-hidden="true">
      <Icon name={look.icon} className="placeholder-icon" />
      <span className="placeholder-note">עוד אין תמונה</span>
    </span>
  )
}
