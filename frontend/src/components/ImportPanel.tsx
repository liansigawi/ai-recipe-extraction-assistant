import { useEffect, useId, useRef, useState } from 'react'
import { errorMessage, getExtractionInfo, importText } from '../api'
import type { ExtractionInfo, Recipe } from '../types'

const MAX_CHARACTERS = 20_000 // the backend's limit (MAX_IMPORT_CHARACTERS)
const STORAGE_KEY = 'recipe-notebook:import-text'

// The pasted text is kept in this browser (localStorage) until an import succeeds, so a
// failure, a closed tab or a reload never loses it. Storage can be unavailable (private
// windows, blocked site data), so every access is wrapped: without it, the text simply
// lives only as long as the page.
function readStoredText(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

function storeText(text: string): void {
  try {
    if (text === '') localStorage.removeItem(STORAGE_KEY)
    else localStorage.setItem(STORAGE_KEY, text)
  } catch {
    // Not available: nothing else to do.
  }
}

interface ImportPanelProps {
  /** Called with the saved draft when an import succeeds. */
  onImported: (draft: Recipe) => void
  onCancel: () => void
}

export default function ImportPanel({ onImported, onCancel }: ImportPanelProps) {
  const id = useId()
  // A function given to useState runs once, on the first render: start from the kept text.
  const [text, setText] = useState(readStoredText)
  const [info, setInfo] = useState<ExtractionInfo | null>(null)
  const [infoCheck, setInfoCheck] = useState(0) // changing it asks the backend again ("check again")
  const [working, setWorking] = useState<'model' | 'manual' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)

  // Who reads the text: Claude (sent to Anthropic) or a local model (stays on this computer).
  const local = info?.local ?? false
  const readLabel = local ? 'קריאה עם המודל המקומי' : 'קריאה עם Claude'

  useEffect(() => {
    textRef.current?.focus()
  }, [])

  // Can imports use the model right now? (An API key for Claude; Ollama running, for a local model.)
  useEffect(() => {
    let ignore = false
    getExtractionInfo().then(
      (answer) => {
        if (!ignore) setInfo(answer)
      },
      () => {
        // The import itself will report the problem, with a message for it.
      },
    )
    return () => {
      ignore = true
    }
  }, [infoCheck])

  function change(value: string) {
    setText(value)
    storeText(value)
    setError(null)
  }

  async function start(useModel: boolean) {
    if (working !== null) return
    if (text.trim() === '') {
      setError('הדביקו קודם את טקסט המתכון.')
      textRef.current?.focus()
      return
    }
    if (text.length > MAX_CHARACTERS) {
      setError(`הטקסט ארוך מדי: עד ${MAX_CHARACTERS.toLocaleString('he-IL')} תווים. השאירו רק את המתכון.`)
      textRef.current?.focus()
      return
    }
    setWorking(useModel ? 'model' : 'manual')
    setError(null)
    try {
      const draft = await importText(text, useModel)
      storeText('') // imported: the draft and its original are in the database now
      onImported(draft)
    } catch (failure) {
      setError(errorMessage(failure)) // the text stays in the box, and in storage
      setWorking(null)
    }
  }

  const tooLong = text.length > MAX_CHARACTERS

  return (
    <section className="import-panel" aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`} className="recipe-title">
        ייבוא מתכון מטקסט
      </h2>
      <p className="field-hint">
        הדביקו מתכון: כיתוב מאינסטגרם, טקסט מאתר או מהודעה. מודל שפה יסדר אותו לטיוטה, ואתם תבדקו אותה מול הטקסט המקורי ותשמרו.
      </p>

      <div className="editor-field">
        <label htmlFor={`${id}-text`} className="field-label">
          טקסט המתכון
        </label>
        <textarea
          ref={textRef}
          id={`${id}-text`}
          dir="auto"
          rows={14}
          value={text}
          readOnly={working !== null}
          aria-invalid={tooLong}
          aria-describedby={`${id}-count`}
          onChange={(event) => change(event.target.value)}
        />
        <p id={`${id}-count`} className={tooLong ? 'field-error' : 'field-hint'}>
          {text.length.toLocaleString('he-IL')} מתוך {MAX_CHARACTERS.toLocaleString('he-IL')} תווים. הטקסט נשמר בדפדפן הזה עד
          שהייבוא מצליח.
        </p>
      </div>

      {info !== null && !info.configured && (
        <div className="form-note">
          <p>
            {info.problem === 'ollama_unreachable' && 'Ollama לא פועל במחשב הזה. הפעילו את Ollama (מתפריט התחל) ובדקו שוב.'}
            {info.problem === 'ollama_model_missing' && (
              <>
                המודל <bdi>{info.model}</bdi> עוד לא הורד ל-Ollama. הריצו בטרמינל <bdi>ollama pull {info.model}</bdi> ובדקו שוב.
              </>
            )}
            {info.problem === 'no_api_key' &&
              'לא הוגדר מפתח ל-Claude API בשרת. ההוראות ב-README, בסעיף "Connect the Claude API".'}{' '}
            בינתיים אפשר לשמור את הטקסט בלי עיבוד ולמלא את המתכון בעצמכם.
          </p>
          {info.local && (
            <button type="button" className="button" onClick={() => setInfoCheck((count) => count + 1)}>
              בדיקה שוב
            </button>
          )}
        </div>
      )}
      {info !== null && info.configured && !info.local && (
        <p className="field-hint">
          בלחיצה על "{readLabel}" הטקסט ורשימת הקטגוריות נשלחים ל-Anthropic (מודל <bdi>{info.model}</bdi>). הטקסט המקורי נשמר כפי שהוא,
          לצד הטיוטה.
        </p>
      )}
      {info !== null && info.configured && info.local && (
        <p className="field-hint">
          בלחיצה על "{readLabel}" הטקסט נקרא כאן, במחשב הזה, על ידי <bdi>{info.model}</bdi> (Ollama), ולא נשלח לשום מקום. הטקסט
          המקורי נשמר כפי שהוא, לצד הטיוטה.
        </p>
      )}

      {/* <output> is announced by screen readers when its text changes. */}
      <output className="working-note">
        {working === 'model' && (local ? 'המודל המקומי קורא את המתכון… בדרך כלל זה לוקח עד דקה.' : 'Claude קורא את המתכון… בדרך כלל זה לוקח פחות מדקה.')}
      </output>
      {error !== null && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}

      <div className="button-row">
        <button
          type="button"
          className="button-primary"
          disabled={info !== null && !info.configured}
          onClick={() => start(true)}
        >
          {working === 'model' ? 'קורא…' : readLabel}
        </button>
        <button type="button" className="button" onClick={() => start(false)}>
          {working === 'manual' ? 'שומר…' : 'שמירה בלי עיבוד'}
        </button>
        <button type="button" className="button" onClick={onCancel}>
          ביטול
        </button>
      </div>
    </section>
  )
}
