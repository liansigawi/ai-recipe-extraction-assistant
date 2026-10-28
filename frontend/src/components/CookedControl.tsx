import { useState } from 'react'
import { errorMessage, setCooked } from '../api'
import type { Recipe } from '../types'
import Icon from './Icon'

interface CookedBadgeProps {
  cooked: boolean
  /** While its change is being saved: further clicks do nothing. */
  saving: boolean
  /** The id of the card's title, which the button describes. */
  describedBy: string
  onToggle: () => void
}

// On every card, in the same corner: text and an icon, not only a color. A toggle button of its own,
// beside the card's button (never inside it), so a click changes the mark without opening the recipe.
// Its name stays "כבר הכנתי" and aria-pressed says whether it is on; the card's title describes it.
export function CookedBadge({ cooked, saving, describedBy, onToggle }: CookedBadgeProps) {
  return (
    <button
      type="button"
      className={`cooked-badge${cooked ? ' is-cooked' : ''}${saving ? ' is-saving' : ''}`}
      aria-label="כבר הכנתי"
      aria-pressed={cooked}
      aria-describedby={describedBy}
      // aria-disabled, not disabled: the button keeps the keyboard focus while it saves.
      aria-disabled={saving || undefined}
      title={cooked ? 'לחיצה מבטלת את הסימון' : 'לחיצה מסמנת שכבר הכנתם'}
      onClick={() => {
        if (!saving) onToggle()
      }}
    >
      <Icon name={cooked ? 'check' : 'circle'} />
      {cooked ? 'כבר הכנתי' : 'טרם הכנתי'}
    </button>
  )
}

interface CookedControlProps {
  recipe: Recipe
  /** Called with the recipe as saved, after each change. */
  onChange: (recipe: Recipe) => void
}

// Beside the recipe's title: "כבר הכנתי" as a checkbox, saved at once, with "ביטול" right after a
// change. App gives each recipe its own control (key), so an undo never carries over to another.
export function CookedControl({ recipe, onChange }: CookedControlProps) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // The mark before the latest change, while that change can still be undone.
  const [before, setBefore] = useState<boolean | null>(null)

  async function save(cooked: boolean, undoable: boolean) {
    if (saving) return
    setSaving(true)
    setError(null)
    try {
      onChange(await setCooked(recipe.id, cooked))
      setBefore(undoable ? !cooked : null)
    } catch (failure) {
      setError(errorMessage(failure))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="cooked-control">
      <label className={recipe.cooked ? 'cooked-toggle is-cooked' : 'cooked-toggle'}>
        <input type="checkbox" className="visually-hidden" checked={recipe.cooked} onChange={(event) => void save(event.target.checked, true)} />
        <span className="cooked-toggle-box">
          <Icon name={recipe.cooked ? 'check' : 'circle'} />
        </span>
        <span className="cooked-toggle-text">
          כבר הכנתי
          {/* The checkbox's state says this to screen readers already. */}
          <small aria-hidden="true">{recipe.cooked ? 'מסומן · לחיצה מבטלת' : 'טרם הכנתי · לחצו לסימון'}</small>
        </span>
      </label>
      {/* A status region: a screen reader announces the change, and "ביטול" is right there. */}
      <output className="cooked-status">
        {before !== null && (
          <>
            {recipe.cooked ? 'סומן: כבר הכנתי.' : 'הסימון הוסר.'}{' '}
            <button type="button" className="text-button" onClick={() => void save(before, false)}>
              ביטול
            </button>
          </>
        )}
      </output>
      {error !== null && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
    </div>
  )
}
