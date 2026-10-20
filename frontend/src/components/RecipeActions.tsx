import { useEffect, useRef, useState } from 'react'
import { errorMessage } from '../api'

interface RecipeActionsProps {
  /** The edit button's text: "עריכה", or "בדיקה ושמירה" for a draft. */
  editLabel?: string
  onEdit: () => void
  /** Deletes the recipe; returns a Promise so this component can wait for it and show a failure. */
  onDelete: () => Promise<void>
}

// Edit and delete buttons for the recipe being shown. Deleting asks first, in the page itself.
export default function RecipeActions({ editLabel = 'עריכה', onEdit, onDelete }: RecipeActionsProps) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)

  // The "Delete" button disappears when the question appears, so move keyboard focus to the safe choice.
  useEffect(() => {
    if (confirming) cancelRef.current?.focus()
  }, [confirming])

  async function handleConfirm() {
    if (deleting) return
    setDeleting(true)
    setError(null)
    try {
      await onDelete() // on success the parent shows another recipe, and this component goes away
    } catch (failure) {
      setError(errorMessage(failure))
      setDeleting(false)
    }
  }

  if (!confirming) {
    return (
      <div className="button-row">
        <button type="button" className="button" onClick={onEdit}>
          {editLabel}
        </button>
        <button type="button" className="button button-danger" onClick={() => setConfirming(true)}>
          מחיקה
        </button>
      </div>
    )
  }
  return (
    // A fieldset groups the question with its answers; a screen reader reads the legend when focus enters.
    <fieldset className="confirm-box">
      <legend>למחוק את המתכון? אי אפשר לבטל מחיקה.</legend>
      <div className="button-row">
        <button type="button" className="button button-danger" onClick={handleConfirm}>
          {deleting ? 'מוחק…' : 'כן, למחוק'}
        </button>
        <button ref={cancelRef} type="button" className="button" onClick={() => setConfirming(false)}>
          לא, להשאיר
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
    </fieldset>
  )
}
