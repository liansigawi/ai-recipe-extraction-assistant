import type { ImportedOriginal } from '../types'
import { CreatorName } from './RecipeView'

interface OriginalTextProps {
  original: ImportedOriginal
  /** Start opened (the review screen) or closed (the recipe view). */
  open?: boolean
  /** Stay at the top of the screen while the form scrolls, for comparing line by line. */
  sticky?: boolean
}

// The text a recipe was imported from, exactly as pasted or read. <details> is the browser's own
// open/close box: its <summary> line is a button that works with the keyboard.
export default function OriginalText({ original, open = false, sticky = false }: OriginalTextProps) {
  // Only web addresses become links (the backend stores the post's canonical https address).
  const postUrl = original.url !== null && original.url.startsWith('https://') ? original.url : null
  return (
    <details className={sticky ? 'original-text original-text-sticky' : 'original-text'} open={open}>
      <summary>
        הטקסט המקורי
        <span className="original-text-meta">
          {original.kind === 'instagram' && ' · כיתוב מהפוסט באינסטגרם'}
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
      {postUrl !== null && (
        <p className="original-text-source">
          {original.kind === 'instagram' ? 'הפוסט: ' : 'הודבק מהפוסט: '}
          <a href={postUrl} target="_blank" rel="noopener noreferrer" dir="ltr">
            {postUrl}
          </a>
          {original.retrieved_from === 'embed_view' &&
            ' (נקרא מתצוגת ההטמעה הציבורית של הפוסט, שעלולה לפגר אחרי עריכות אחרונות)'}
          {original.author !== null && (
            <>
              {' · פורסם על ידי '}
              {[original.author, ...original.coauthors].map((person, index) => (
                <span key={index}>
                  {index > 0 && ', '}
                  <CreatorName creator={person} />
                </span>
              ))}
            </>
          )}
        </p>
      )}
      {/* white-space: pre-wrap (index.css) keeps the line breaks exactly as pasted. */}
      <div className="original-text-body" dir="auto">
        {original.text}
      </div>
    </details>
  )
}
