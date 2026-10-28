import { useEffect, useId, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { chooseCover, errorMessage, fetchPostMedia, removeMedia, uploadMedia } from '../api'
import { instagramPostOf, pictureUrl, reportText } from '../media'
import type { Recipe, RecipeMediaItem } from '../types'

const MAX_UPLOAD_BYTES = 20_000_000 // the backend's limit (MAX_UPLOAD_BYTES)
const IMAGE_TYPES = 'image/jpeg,image/png,image/webp,image/gif'

/** A picture, or a clear placeholder when there is none or its file cannot be loaded. */
export function MediaImage({ src, alt, className }: { src: string | null; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  if (src === null || failed) {
    return (
      <span className={`media-missing ${className ?? ''}`} role={alt ? 'img' : undefined} aria-label={alt || undefined} aria-hidden={alt ? undefined : true}>
        {src === null ? 'אין תמונה' : 'התמונה לא נמצאה'}
      </span>
    )
  }
  return <img src={src} alt={alt} className={className} loading="lazy" onError={() => setFailed(true)} />
}

function itemLabel(item: RecipeMediaItem, index: number, count: number, isCover: boolean): string {
  const kind = item.kind === 'image' ? 'תמונה' : item.status === 'saved' ? 'סרטון' : 'סרטון שלא נשמר במחשב'
  return `${kind} ${index + 1} מתוך ${count}${isCover ? ', התמונה הראשית' : ''}`
}

interface MediaGalleryProps {
  recipe: Recipe
  /** Called with the recipe after a change to its media. Without it the gallery only shows. */
  onChange?: (recipe: Recipe) => void
}

// The recipe's pictures and videos, in the post's order, then uploads. A thumbnail opens the viewer.
export default function MediaGallery({ recipe, onChange }: MediaGalleryProps) {
  const id = useId()
  const [open, setOpen] = useState<number | null>(null)
  const [working, setWorking] = useState<'fetch' | 'upload' | null>(null)
  const [message, setMessage] = useState<{ text: string; problems?: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const media = recipe.media
  const post = instagramPostOf(recipe)

  function changed(next: Recipe, text?: string, problems?: string[]) {
    onChange?.(next)
    setMessage(text === undefined ? null : { text, problems })
  }

  async function fetchFromPost() {
    if (working !== null) return
    setWorking('fetch')
    setError(null)
    setMessage(null)
    try {
      const { recipe: next, report } = await fetchPostMedia(recipe.id)
      changed(next, reportText(report), report.problems)
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setWorking(null)
    }
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = [...(event.target.files ?? [])]
    event.target.value = '' // the same file can be chosen again later
    if (files.length === 0 || working !== null) return
    const wrong = files.find((file) => !IMAGE_TYPES.split(',').includes(file.type) || file.size > MAX_UPLOAD_BYTES)
    if (wrong !== undefined) {
      setError(wrong.size > MAX_UPLOAD_BYTES ? `"${wrong.name}" גדולה מדי: עד 20 MB.` : `"${wrong.name}" אינה תמונה מסוג JPEG, PNG, WebP או GIF.`)
      return
    }
    setWorking('upload')
    setError(null)
    setMessage(null)
    try {
      let next = recipe
      for (const file of files) next = await uploadMedia(recipe.id, file)
      changed(next, files.length === 1 ? 'התמונה נוספה.' : `${files.length} תמונות נוספו.`)
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setWorking(null)
    }
  }

  async function act(action: () => Promise<Recipe>, text: string) {
    setError(null)
    try {
      changed(await action(), text)
    } catch (failure) {
      setError(errorMessage(failure))
    }
  }

  return (
    <section className="recipe-section media-section" aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} className="section-title">
        תמונות וסרטונים
      </h3>
      {media.length === 0 ? (
        <p className="field-hint">אין עדיין תמונות או סרטונים.{post !== null && onChange && ' אפשר לשלוף אותם מהפוסט באינסטגרם.'}</p>
      ) : (
        <ul className="media-grid">
          {media.map((item, index) => {
            const isCover = item.id === recipe.cover_id
            return (
              <li key={item.id}>
                <button type="button" className="media-thumb" aria-label={itemLabel(item, index, media.length, isCover)} onClick={() => setOpen(index)}>
                  <MediaImage src={pictureUrl(item)} alt="" className="media-thumb-image" />
                  {item.kind === 'video' && (
                    <span className={item.status === 'saved' ? 'media-badge' : 'media-badge media-badge-remote'}>
                      {item.status === 'saved' ? '▶ סרטון' : '▶ באינסטגרם בלבד'}
                    </span>
                  )}
                  {isCover && <span className="media-cover-badge">ראשית</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {onChange !== undefined && (
        <div className="button-row">
          <label className="button file-button">
            {working === 'upload' ? 'מעלה…' : 'העלאת תמונה'}
            <input type="file" accept={IMAGE_TYPES} multiple className="visually-hidden" disabled={working !== null} onChange={upload} />
          </label>
          {post !== null && (
            <button type="button" className="button" disabled={working !== null} onClick={fetchFromPost}>
              {working === 'fetch' ? 'שולף…' : 'שליפת מדיה מהפוסט'}
            </button>
          )}
        </div>
      )}
      <output className="working-note">
        {working === 'fetch' && 'קורא את הפוסט באינסטגרם ושומר את התמונות והסרטונים במחשב… זה יכול לקחת עד כמה דקות.'}
      </output>
      {/* Always present, so screen readers announce what appears in it. */}
      <output className="media-message">{message?.text}</output>
      {message?.problems !== undefined && message.problems.length > 0 && (
        <details className="media-problems">
          <summary>פרטים</summary>
          <ul>
            {message.problems.map((problem, index) => (
              <li key={index}>{problem}</li>
            ))}
          </ul>
        </details>
      )}
      {error !== null && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {open !== null && media[open] !== undefined && (
        <MediaViewer
          title={recipe.title}
          media={media}
          index={open}
          coverId={recipe.cover_id}
          onIndex={setOpen}
          onClose={() => setOpen(null)}
          onCover={onChange && ((mediaId) => act(() => chooseCover(recipe.id, mediaId), mediaId === null ? 'התמונה הראשית תהיה הראשונה בגלריה.' : 'התמונה הראשית נבחרה.'))}
          onRemove={
            onChange &&
            ((mediaId) => {
              setOpen(null)
              void act(() => removeMedia(recipe.id, mediaId), 'הפריט הוסר מהמתכון.')
            })
          }
        />
      )}
    </section>
  )
}

interface MediaViewerProps {
  title: string
  media: RecipeMediaItem[]
  index: number
  coverId: number | null
  onIndex: (index: number) => void
  onClose: () => void
  onCover?: (mediaId: number | null) => void
  onRemove?: (mediaId: number) => void
}

// One item enlarged, in the browser's own modal <dialog>: Escape closes it, and focus stays inside.
function MediaViewer({ title, media, index, coverId, onIndex, onClose, onCover, onRemove }: MediaViewerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const item = media[index]
  const isCover = item.id === coverId
  const hasPicture = pictureUrl(item) !== null

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog !== null && !dialog.open) dialog.showModal()
  }, [])

  function keyDown(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.target instanceof HTMLVideoElement) return // the video's own keys (seeking)
    // Right to left: the next item is to the left.
    if (event.key === 'ArrowLeft' && index < media.length - 1) onIndex(index + 1)
    if (event.key === 'ArrowRight' && index > 0) onIndex(index - 1)
  }

  return (
    <dialog ref={dialogRef} className="media-viewer" aria-label={`${title}: ${itemLabel(item, index, media.length, isCover)}`} onClose={onClose} onKeyDown={keyDown}>
      <div className="viewer-stage">
        {item.kind === 'image' && <MediaImage key={item.id} src={item.file?.url ?? null} alt={`תמונה ${index + 1} של ${title}`} className="viewer-media" />}
        {item.kind === 'video' && item.status === 'saved' && item.file !== null && (
          // controls, and no autoplay: it plays only when asked. preload="metadata": only its length, until then.
          // oxlint-disable-next-line jsx-a11y/media-has-caption -- Instagram gives no caption file; the post's own text is under "הטקסט המקורי".
          <video key={item.id} className="viewer-media" src={item.file.url} poster={item.thumbnail?.url} controls preload="metadata" playsInline>
            הדפדפן לא מצליח להציג את הסרטון.
          </video>
        )}
        {item.kind === 'video' && item.status === 'thumbnail_only' && (
          <>
            <MediaImage key={item.id} src={item.thumbnail?.url ?? null} alt={`תמונה מתוך סרטון ${index + 1} של ${title}`} className="viewer-media" />
            <p className="viewer-note">
              הסרטון עצמו לא נשמר במחשב הזה; זו תמונה מתוכו.{' '}
              {item.post_url !== null && (
                <a href={item.post_url} target="_blank" rel="noreferrer">
                  לצפייה בסרטון בפוסט באינסטגרם
                </a>
              )}
            </p>
          </>
        )}
      </div>
      <p className="viewer-caption">
        {itemLabel(item, index, media.length, isCover)}
        {item.origin === 'upload' ? ' · הועלתה מהמחשב' : item.origin === 'website' ? ' · מדף המתכון' : ' · מהפוסט'}
        {item.origin === 'instagram' && item.post_url !== null && item.status !== 'thumbnail_only' && (
          <>
            {' · '}
            <a href={item.post_url} target="_blank" rel="noreferrer">
              לפוסט המקורי
            </a>
          </>
        )}
      </p>
      <div className="button-row viewer-buttons">
        <button type="button" className="button" disabled={index === 0} onClick={() => onIndex(index - 1)}>
          הקודם
        </button>
        <button type="button" className="button" disabled={index === media.length - 1} onClick={() => onIndex(index + 1)}>
          הבא
        </button>
        {/* The cover by default (the first picture, nothing chosen) needs neither button. */}
        {onCover !== undefined && hasPicture && (item.is_cover || !isCover) && (
          <button type="button" className="button" onClick={() => onCover(item.is_cover ? null : item.id)}>
            {item.is_cover ? 'ביטול הבחירה כתמונה ראשית' : 'קביעה כתמונה ראשית'}
          </button>
        )}
        {onRemove !== undefined && (
          <button
            type="button"
            className="button button-danger"
            onClick={() => {
              if (window.confirm('להסיר את הפריט מהמתכון? אם הוא הגיע מהפוסט, אפשר לשלוף אותו שוב.')) onRemove(item.id)
            }}
          >
            הסרה מהמתכון
          </button>
        )}
        <button type="button" className="button-primary" onClick={() => dialogRef.current?.close()}>
          סגירה
        </button>
      </div>
    </dialog>
  )
}
