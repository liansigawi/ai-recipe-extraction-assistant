// How a category looks: its drawing and its color, the same on a recipe without a picture, on the
// category's filter chip and on the card's dot. No React.
import type { CategoryRef } from './types'

export type IconName =
  | 'check'
  | 'circle'
  | 'search'
  | 'plus'
  | 'close'
  | 'play'
  | 'link'
  | 'back'
  | 'book'
  | 'cake'
  | 'pot'
  | 'bowl'
  | 'glass'
  | 'leaf'
  | 'soup'
  | 'side'
  | 'jar'
  | 'utensils'

export type Tone = 'dessert' | 'meat' | 'light' | 'drink' | 'salad' | 'soup' | 'side' | 'spread' | 'none' | 'other'

/** By the category's name, so a category you add ("קינוחים לחג") looks like its kind; any other
 * category gets the utensils, and an unclassified recipe the notebook. */
export function categoryLook(category: CategoryRef | null): { icon: IconName; tone: Tone } {
  if (category === null) return { icon: 'book', tone: 'none' }
  const name = category.name
  if (name.includes('קינוח')) return { icon: 'cake', tone: 'dessert' }
  if (name.includes('בשרי') || name.includes('בישול')) return { icon: 'pot', tone: 'meat' }
  if (name.includes('קליל')) return { icon: 'bowl', tone: 'light' }
  if (name.includes('משק') || name.includes('שתי')) return { icon: 'glass', tone: 'drink' }
  if (name.includes('סלט')) return { icon: 'leaf', tone: 'salad' }
  if (name.includes('מרק')) return { icon: 'soup', tone: 'soup' }
  if (name.includes('תוספ')) return { icon: 'side', tone: 'side' }
  if (name.includes('ממרח') || name.includes('מטבל') || name.includes('רטב')) return { icon: 'jar', tone: 'spread' }
  return { icon: 'utensils', tone: 'other' }
}

/** "קינוחים · קינוחים בריאים", or the subcategory alone when its name already starts with the
 * category's ("קינוחים רגילים"), or "לא מסווג". */
/** The healthy-style attribute's name, and its value as words (null: not decided, nothing to say). */
export const HEALTHY_LABEL = 'קינוח בריא'

export function healthyLabel(healthy: boolean | null | undefined): string | null {
  if (healthy === true) return HEALTHY_LABEL
  if (healthy === false) return `לא ${HEALTHY_LABEL}`
  return null
}

export function categoryLabel(category: CategoryRef | null, subcategory: CategoryRef | null = null): string {
  if (category === null) return 'לא מסווג'
  if (subcategory === null) return category.name
  return subcategory.name.startsWith(category.name) ? subcategory.name : `${category.name} · ${subcategory.name}`
}
