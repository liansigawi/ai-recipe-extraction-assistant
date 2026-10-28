import type { Ref } from 'react'
import type { Recipe } from '../types'
import Icon from './Icon'

/** What a badge click needs to tell: the recipe left the filtered gallery (with "ביטול"), or the
 * mark could not be saved. */
export type GalleryMessage =
  | { kind: 'hidden'; recipe: Recipe; previous: boolean }
  | { kind: 'error'; title: string; text: string }

interface GalleryNoticeProps {
  message: GalleryMessage | null
  onUndo: () => void
  onClose: () => void
  undoRef?: Ref<HTMLButtonElement>
  undoing: boolean
}

// A short note at the bottom of the screen. It stays until it is closed, the mark changes again, or the
// page changes: no time limit to read it or to reach "ביטול".
export default function GalleryNotice({ message, onUndo, onClose, undoRef, undoing }: GalleryNoticeProps) {
  return (
    <div className="gallery-notice-region">
      {/* <output>: a status region, always in the page, so a screen reader announces what appears in it.
          It holds phrasing content only, hence the spans. */}
      <output className="gallery-notice-status">
        {message?.kind === 'hidden' && (
          <span className="gallery-notice">
            <span>
              {message.recipe.cooked ? 'סומן "כבר הכנתי"' : 'הסימון "כבר הכנתי" הוסר'}: <bdi>{message.recipe.title}</bdi>. הסינון
              הנוכחי לא מציג אותו.
            </span>
            <button
              ref={undoRef}
              type="button"
              className="gallery-notice-undo"
              aria-disabled={undoing || undefined}
              onClick={() => {
                if (!undoing) onUndo()
              }}
            >
              ביטול
            </button>
            <button type="button" className="gallery-notice-close" aria-label="סגירת ההודעה" onClick={onClose}>
              <Icon name="close" />
            </button>
          </span>
        )}
      </output>
      {message?.kind === 'error' && (
        <div className="gallery-notice is-error" role="alert">
          <p>
            הסימון של <bdi>{message.title}</bdi> לא נשמר: {message.text}
          </p>
          <button type="button" className="gallery-notice-close" aria-label="סגירת ההודעה" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
      )}
    </div>
  )
}
