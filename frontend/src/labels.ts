// Display names shared by several components.
import type { IssueKind, Resolution, SourceKind } from './types'

export const SOURCE_LABELS: Record<SourceKind, string> = {
  instagram: 'אינסטגרם',
  website: 'אתר',
  screenshot: 'צילום מסך',
  text: 'טקסט שהודבק',
  manual: 'הוזן ידנית',
}

/** Every source kind, in the order the editor offers them. */
export const SOURCE_KINDS = Object.keys(SOURCE_LABELS) as SourceKind[]

/** A short title for each kind of review issue. */
export const ISSUE_LABELS: Record<IssueKind, string> = {
  ingredient_only_in_steps: 'מצרך שמופיע רק בהוראות',
  unclear_text: 'טקסט לא ברור',
  missing_information: 'מידע חסר',
  ambiguous_alternative: 'חלופה לא ברורה',
  multiple_recipes: 'כמה מתכונים בטקסט',
  other: 'לבדיקה',
  missing_title: 'כותרת',
  quantity_not_in_line: 'כמות',
  not_found_in_source: 'לא נמצא בטקסט המקורי',
  classification_unresolved: 'קטגוריה',
  not_extracted: 'לא עובד',
  unused_text: 'קטע שלא שובץ',
  invalid_reference: 'הפניה לא תקינה',
  caption_incomplete: 'כיתוב חלקי',
  media_incomplete: 'תמונות וסרטונים',
}

/** Beside an ingredient line that the app added from the preparation (Ingredient.derived_from). */
export const DERIVED_LABEL = 'מופיע בהוראות ההכנה'

/** Beside a line added from the preparation because you approved it in review (Ingredient.added_in_review). */
export const ADDED_IN_REVIEW_LABEL = 'נוסף מהוראות ההכנה'

/** The label of a line that came from the steps, by who added it: you in review, or the app's rule. */
export const fromStepsLabel = (ingredient: { added_in_review?: boolean }) => (ingredient.added_in_review ? ADDED_IN_REVIEW_LABEL : DERIVED_LABEL)

/** What was done about a review point. */
export const RESOLUTION_LABELS: Record<Resolution, string> = {
  added: 'נוסף למצרכים',
  dismissed: 'התעלמות',
  handled: 'טופל',
}
