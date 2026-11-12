import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, captionFrom, errorMessage, getExtractionInfo, importLink, importText, linkedRecipesFrom } from '../api'
import { LINK_HELP, linkKind, NOT_A_LINK } from '../importLinks'
import type { ExtractionInfo, LinkedRecipe, Recipe } from '../types'

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

/** What to do next after a link could not be imported, added to the reason. */
function fallbackHint(error: unknown, captionInBox: boolean): string {
  if (error instanceof ApiError && (error.code === 'website_invalid_url' || error.code === 'website_forbidden_address')) return ''
  if (error instanceof ApiError && error.code.startsWith('website_')) {
    return 'אפשר להעתיק את המתכון מהדף ולהדביק אותו בתיבה למטה; הקישור יישמר עם המתכון.'
  }
  if (error instanceof ApiError && error.code === 'instagram_caption_incomplete') {
    return captionInBox
      ? 'הכיתוב החלקי הועתק לתיבה למטה: השוו לפוסט באינסטגרם, השלימו את החסר וקראו אותו משם.'
      : 'אפשר להעתיק את הכיתוב המלא מהפוסט ולהדביק אותו בתיבה למטה.'
  }
  if (captionInBox) {
    return 'הכיתוב שנקרא מהפוסט הועתק לתיבה למטה: אפשר לנסות שוב משם, או לשמור אותו בלי עיבוד.'
  }
  if (error instanceof ApiError && error.code.startsWith('instagram_')) {
    return 'אפשר להעתיק את הכיתוב מהפוסט ולהדביק אותו בתיבה למטה; הקישור יישמר עם המתכון.'
  }
  return ''
}

interface ImportPanelProps {
  /** Called with the saved draft when an import succeeds. */
  onImported: (draft: Recipe) => void
  onCancel: () => void
  /** Opens a recipe that already has the post (from the duplicate notice). */
  onOpenRecipe: (id: number) => void
  /** A link from the gallery's import strip... */
  initialUrl?: string
  /** ...read at once. */
  startNow?: boolean
  /** Start in the text box ("להדביק טקסט של מתכון"). */
  focusText?: boolean
}

// An import that stopped because the post is already in the notebook: the recipes that have it, and
// how to repeat the same import as another copy.
interface Duplicate {
  matches: LinkedRecipe[]
  again: () => void
}

export default function ImportPanel({ onImported, onCancel, onOpenRecipe, initialUrl = '', startNow = false, focusText = false }: ImportPanelProps) {
  const id = useId()
  const [url, setUrl] = useState(initialUrl)
  // A function given to useState runs once, on the first render: start from the kept text.
  const [text, setText] = useState(readStoredText)
  // A caption preview that may be cut off, put in the box after a failed read: sent unchanged, the draft says so.
  const [preview, setPreview] = useState<string | null>(null)
  const [info, setInfo] = useState<ExtractionInfo | null>(null)
  const [infoCheck, setInfoCheck] = useState(0) // changing it asks the backend again ("check again")
  const [working, setWorking] = useState<'link' | 'model' | 'manual' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Where the message belongs: under the link (reading the post) or under the text box.
  const [errorAt, setErrorAt] = useState<'link' | 'text'>('text')
  const [duplicate, setDuplicate] = useState<Duplicate | null>(null)
  // The address the person chose to import again although the notebook has it (kept for the paste fallback).
  const [anotherCopyOf, setAnotherCopyOf] = useState<string | null>(null)
  const urlRef = useRef<HTMLInputElement>(null)
  const textRef = useRef<HTMLTextAreaElement>(null)
  // Set once the strip's link was sent: React runs effects twice in development, the import only once.
  const started = useRef(false)
  // The link saved with pasted text, as its source: an Instagram post or a recipe page.
  const textLink = linkKind(url) === 'instagram' || linkKind(url) === 'website' ? url.trim() : ''
  const readingWebsite = linkKind(url) === 'website'

  // Who reads the text: Claude (sent to Anthropic) or a local model (stays on this computer).
  const local = info?.local ?? false
  const readLabel = local ? 'קריאה עם המודל המקומי' : 'קריאה עם Claude'
  const modelReady = info === null || info.configured

  useEffect(() => {
    if (focusText) textRef.current?.focus()
    else urlRef.current?.focus()
    if (startNow && !started.current) {
      started.current = true
      void startLink()
    }
    // Only when the screen opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  /** Put a caption read from the post in the box; asks before replacing other text there. */
  function offerCaption(caption: string): boolean {
    if (text.trim() !== '' && text !== caption && !window.confirm('להחליף את הטקסט שבתיבה בכיתוב שנקרא מהפוסט?')) {
      return false
    }
    setText(caption)
    storeText(caption)
    return true
  }

  /** "ייבוא מהקישור": an Instagram post or a recipe page; the backend chooses how to read it. */
  async function startLink(allowDuplicate = anotherCopyOf === url.trim()) {
    if (working !== null) return
    setErrorAt('link')
    setDuplicate(null)
    const kind = linkKind(url)
    if (kind === 'empty' || kind === 'not_a_link') {
      setError(kind === 'empty' ? 'הדביקו קודם קישור למתכון.' : NOT_A_LINK)
      urlRef.current?.focus()
      return
    }
    setWorking('link')
    setError(null)
    try {
      onImported(await importLink(url.trim(), modelReady, allowDuplicate))
    } catch (failure) {
      const matches = linkedRecipesFrom(failure)
      if (matches !== null) {
        setDuplicate({ matches, again: () => anotherCopy(() => startLink(true)) })
        setWorking(null)
        return
      }
      const caption = captionFrom(failure)
      const inBox = caption !== null && offerCaption(caption)
      const incomplete = failure instanceof ApiError && failure.code === 'instagram_caption_incomplete'
      setPreview(inBox && incomplete ? caption : null)
      setError([errorMessage(failure), fallbackHint(failure, inBox)].filter(Boolean).join(' '))
      setWorking(null)
      const linkIsWrong = ['invalid_instagram_url', 'website_invalid_url', 'website_forbidden_address']
      if (failure instanceof ApiError && linkIsWrong.includes(failure.code)) urlRef.current?.focus()
      else textRef.current?.focus()
    }
  }

  /** "ייבוא עותק נוסף": the same import again, allowed although the post is already here. */
  function anotherCopy(repeat: () => void) {
    setAnotherCopyOf(url.trim())
    setDuplicate(null)
    repeat()
  }

  async function start(useModel: boolean, allowDuplicate = textLink !== '' && anotherCopyOf === textLink) {
    if (working !== null) return
    setErrorAt('text')
    setDuplicate(null)
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
      const draft = await importText(text, useModel, {
        url: textLink,
        possiblyIncomplete: preview !== null && text === preview,
        allowDuplicate,
      })
      storeText('') // imported: the draft and its original are in the database now
      onImported(draft)
    } catch (failure) {
      const matches = linkedRecipesFrom(failure)
      if (matches !== null) setDuplicate({ matches, again: () => anotherCopy(() => start(useModel, true)) })
      else setError(errorMessage(failure)) // the text stays in the box, and in storage
      setWorking(null)
    }
  }

  const tooLong = text.length > MAX_CHARACTERS

  return (
    <section className="import-panel" aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`} className="recipe-title">
        ייבוא מתכון
      </h2>
      <p className="field-hint">
        הדביקו קישור למתכון, או את טקסט המתכון. מודל שפה יסדר אותו לטיוטה, ואתם תבדקו אותה מול הטקסט המקורי ותשמרו.
      </p>

      <div className="editor-field">
        <label htmlFor={`${id}-url`} className="field-label">
          קישור למתכון
        </label>
        <div className="url-row">
          <input
            ref={urlRef}
            id={`${id}-url`}
            type="url"
            dir="ltr"
            inputMode="url"
            autoComplete="off"
            placeholder="https://www.instagram.com/p/…"
            value={url}
            readOnly={working !== null}
            aria-describedby={`${id}-url-hint`}
            onChange={(event) => {
              setUrl(event.target.value)
              setError(null)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') void startLink()
            }}
          />
          <button type="button" className="button-primary" onClick={() => void startLink()}>
            {working === 'link' ? 'קורא…' : modelReady ? 'ייבוא מהקישור' : 'ייבוא מהקישור בלי עיבוד'}
          </button>
        </div>
        <p id={`${id}-url-hint`} className="field-hint">
          {LINK_HELP} מאינסטגרם נקרא הכיתוב של הפוסט הציבורי, בלי התחברות. מאתר נקראים נתוני המתכון שבדף, ואם אין כאלה, הטקסט
          הראשי שלו. מה שנקרא נשמר כפי שהוא לצד הטיוטה, עם הקישור.
        </p>
        {/* <output> is announced by screen readers when its text changes. */}
        <output className="working-note">
          {working === 'link' &&
            (readingWebsite
              ? modelReady
                ? `קורא את דף המתכון, ואז ${local ? 'המודל המקומי' : 'Claude'} מסדר אותו לטיוטה… בדרך כלל עד דקה.`
                : 'קורא את דף המתכון…'
              : modelReady
                ? `קורא את הכיתוב מהפוסט באינסטגרם, ואז ${local ? 'המודל המקומי' : 'Claude'} מסדר אותו לטיוטה… בדרך כלל עד דקה.`
                : 'קורא את הכיתוב מהפוסט באינסטגרם…')}
        </output>
        {error !== null && errorAt === 'link' && (
          <p role="alert" className="form-alert">
            {error}
          </p>
        )}
        {duplicate !== null && errorAt === 'link' && <DuplicateNotice duplicate={duplicate} onOpen={onOpenRecipe} page={readingWebsite} />}
      </div>

      <p className="import-divider">או הדביקו את הטקסט</p>

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
          {textLink !== '' && ' הקישור שלמעלה יישמר עם המתכון כמקור.'}
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
              'לא הוגדר מפתח ל-Claude API בשרת. מפתח נדרש רק לקריאה עם Claude API: ההוראות ב-docs/setup.md, בסעיף "Connect the Claude API". המודל המקומי (Ollama) לא צריך מפתח: ההוראות באותו קובץ, בסעיף "Run extraction on this computer (Ollama)".'}{' '}
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
      {duplicate !== null && errorAt === 'text' && <DuplicateNotice duplicate={duplicate} onOpen={onOpenRecipe} page={readingWebsite} />}
      {error !== null && errorAt === 'text' && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}

      <div className="button-row">
        <button type="button" className="button-primary" disabled={!modelReady} onClick={() => start(true)}>
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

/** The post or page is already in the notebook: open a recipe that has it, or import another copy.
 * Nothing is replaced. */
function DuplicateNotice({ duplicate, onOpen, page }: { duplicate: Duplicate; onOpen: (id: number) => void; page: boolean }) {
  const { matches, again } = duplicate
  return (
    <div role="alert" className="duplicate-notice">
      <p>
        <strong>{page ? 'הדף הזה כבר במחברת' : 'הפוסט הזה כבר במחברת'}</strong>
        {matches.length === 1 ? ', במתכון:' : `, ב-${matches.length} מתכונים:`}
      </p>
      <ul className="duplicate-list">
        {matches.map((match) => (
          <li key={match.id}>
            <span dir="auto">{match.title}</span>
            <span className={match.status === 'draft' ? 'badge-draft' : 'badge-saved'}>{match.status === 'draft' ? 'טיוטה' : 'מתכון'}</span>
            <button type="button" className="button" aria-label={`פתיחת ${match.title}`} onClick={() => onOpen(match.id)}>
              פתיחה
            </button>
          </li>
        ))}
      </ul>
      <p className="field-hint">אפשר לפתוח את המתכון הקיים, או לייבא עותק נוסף. שום מתכון קיים לא ישתנה.</p>
      <div className="button-row">
        <button type="button" className="button" onClick={again}>
          ייבוא עותק נוסף
        </button>
      </div>
    </div>
  )
}
