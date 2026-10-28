import { useId, useState, type FormEvent, type Ref } from 'react'
import { LINK_HELP, linkKind, NOT_A_LINK, WEBSITE_NOT_YET } from '../importLinks'
import Icon from './Icon'

interface QuickImportProps {
  id: string
  inputRef?: Ref<HTMLInputElement>
  /** An Instagram link: read it now, on the import screen. */
  onImportLink: (url: string) => void
  onPasteText: () => void
  onCreate: () => void
}

// "ייבוא מתכון מקישור" in one row above the gallery: the link, its button, and the other ways to add a
// recipe. Only Instagram links are imported today; for any other link the strip says so, and offers
// pasting the recipe's text instead.
export default function QuickImport({ id, inputRef, onImportLink, onPasteText, onCreate }: QuickImportProps) {
  const fieldId = useId()
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState<{ tone: 'later' | 'error'; text: string } | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    const kind = linkKind(url)
    if (kind === 'instagram') return onImportLink(url.trim())
    if (kind === 'empty') setMessage({ tone: 'error', text: 'הדביקו קודם קישור למתכון.' })
    else if (kind === 'website') setMessage({ tone: 'later', text: WEBSITE_NOT_YET })
    else setMessage({ tone: 'error', text: NOT_A_LINK })
  }

  return (
    <section id={id} className="quick-import" aria-labelledby={`${fieldId}-title`}>
      <h2 id={`${fieldId}-title`} className="quick-import-title">
        <Icon name="link" />
        ייבוא מתכון מקישור
      </h2>
      {/* noValidate: the page checks the link itself and says what is wrong in Hebrew. */}
      <form className="quick-import-form" onSubmit={submit} noValidate>
        <label htmlFor={fieldId} className="visually-hidden">
          קישור למתכון
        </label>
        <input
          ref={inputRef}
          id={fieldId}
          type="url"
          dir="ltr"
          inputMode="url"
          autoComplete="off"
          placeholder="https://www.instagram.com/p/…"
          value={url}
          aria-describedby={`${fieldId}-help ${fieldId}-message`}
          onChange={(event) => {
            setUrl(event.target.value)
            setMessage(null)
          }}
        />
        <button type="submit" className="button-primary">
          ייבוא
        </button>
      </form>
      <p id={`${fieldId}-help`} className="quick-import-help">
        {LINK_HELP} אפשר גם{' '}
        <button type="button" className="text-button" onClick={onPasteText}>
          להדביק טקסט של מתכון
        </button>{' '}
        או{' '}
        <button type="button" className="text-button" onClick={onCreate}>
          לכתוב מתכון חדש
        </button>
        .
      </p>
      <p id={`${fieldId}-message`} className={message === null ? 'quick-import-message' : `quick-import-message is-${message.tone}`} aria-live="polite">
        {message?.text}
        {message?.tone === 'later' && (
          <>
            {' '}
            <button type="button" className="text-button" onClick={onPasteText}>
              להדבקת הטקסט
            </button>
          </>
        )}
      </p>
    </section>
  )
}
