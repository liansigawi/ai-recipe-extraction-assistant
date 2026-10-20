// Display names shared by several components.
import type { SourceKind } from './types'

export const SOURCE_LABELS: Record<SourceKind, string> = {
  instagram: 'אינסטגרם',
  website: 'אתר',
  screenshot: 'צילום מסך',
  text: 'טקסט שהודבק',
  manual: 'הוזן ידנית',
}

/** Every source kind, in the order the editor offers them. */
export const SOURCE_KINDS = Object.keys(SOURCE_LABELS) as SourceKind[]
