interface RowButtonsProps {
  /** What the row is, for the buttons' names: "מצרך 2" gives "הזזת מצרך 2 למעלה". */
  label: string
  index: number
  count: number
  onMove: (delta: -1 | 1) => void
  onRemove: () => void
}

// Move up, move down and remove, for one row of an editable list. The buttons show only
// a symbol, so aria-label gives each one a spoken name (and title a tooltip).
export default function RowButtons({ label, index, count, onMove, onRemove }: RowButtonsProps) {
  const up = `הזזת ${label} למעלה`
  const down = `הזזת ${label} למטה`
  const remove = `הסרת ${label}`
  return (
    <div className="row-buttons">
      <button type="button" className="icon-button" aria-label={up} title={up} disabled={index === 0} onClick={() => onMove(-1)}>
        ▲
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label={down}
        title={down}
        disabled={index === count - 1}
        onClick={() => onMove(1)}
      >
        ▼
      </button>
      <button type="button" className="icon-button" aria-label={remove} title={remove} onClick={onRemove}>
        ✕
      </button>
    </div>
  )
}
