// Display names shared by several components.
import type { IssueKind, SourceKind } from './types'

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
