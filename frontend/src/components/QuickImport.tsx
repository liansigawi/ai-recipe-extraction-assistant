import { useId, useState, type FormEvent, type Ref } from 'react'
import { LINK_HELP, linkKind, NOT_A_LINK } from '../importLinks'
import Icon from './Icon'

interface QuickImportProps {
  id: string
  inputRef?: Ref<HTMLInputElement>
  /** An Instagram post or a recipe page: read it now, on the import screen. */
  onImportLink: (url: string) => void
  onPasteText: () => void
  onCreate: () => void
}

// "ייבוא מתכון מקישור" in one row above the gallery: the link, its button, and the other ways to add a
// recipe. Any web link goes on to the import screen, which reads it (the backend chooses how).
export default function QuickImport({ id, inputRef, onImportLink, onPasteText, onCreate }: QuickImportProps) {
  const fieldId = useId()
  const [url, setUrl] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    const kind = linkKind(url)
    if (kind === 'instagram' || kind === 'website') return onImportLink(url.trim())
    setMessage(kind === 'empty' ? 'הדביקו קודם קישור למתכון.' : NOT_A_LINK)
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
      <p id={`${fieldId}-message`} className="quick-import-message" aria-live="polite">
        {message}
      </p>
    </section>
  )
}
