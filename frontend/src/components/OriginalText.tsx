import type { ImportedOriginal } from '../types'

interface OriginalTextProps {
  original: ImportedOriginal
  /** Start opened (the review screen) or closed (the recipe view). */
  open?: boolean
  /** Stay at the top of the screen while the form scrolls, for comparing line by line. */
  sticky?: boolean
}

// The text a recipe was imported from, exactly as pasted. <details> is the browser's own
// open/close box: its <summary> line is a button that works with the keyboard.
export default function OriginalText({ original, open = false, sticky = false }: OriginalTextProps) {
  return (
    <details className={sticky ? 'original-text original-text-sticky' : 'original-text'} open={open}>
      <summary>
        הטקסט המקורי
        <span className="original-text-meta">
          {original.model !== null ? (
            <>
              {' '}
              · נקרא על ידי <bdi>{original.model}</bdi>
            </>
          ) : (
            ' · נשמר בלי עיבוד'
          )}
        </span>
      </summary>
      {/* white-space: pre-wrap (index.css) keeps the line breaks exactly as pasted. */}
      <div className="original-text-body" dir="auto">
        {original.text}
      </div>
    </details>
  )
}
