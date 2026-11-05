import { useId } from 'react'
import type { IssueRow, RecipeForm, ResolvedRow } from '../editorForm'
import { ISSUE_LABELS, RESOLUTION_LABELS } from '../labels'
import { addProposed, listsIngredient, proposalOf, resolvePoint, targetGroup, undoResolved } from '../reviewPoints'

interface ReviewIssuesProps {
  form: RecipeForm
  onChange: (form: RecipeForm) => void
}

// What the import flagged for review, and what review decided. A point about an ingredient that only the steps
// name offers its line, shown before anything is added, with two explicit actions: add it, or ignore the point.
// Any other point is marked done. Every decision can be undone, and is saved with the form ("save as draft" keeps
// the points still open; "save as recipe" ends the review); until then it is marked as not saved yet.
export default function ReviewIssues({ form, onChange }: ReviewIssuesProps) {
  const id = useId()
  const { issues, resolved } = form
  return (
    <section className="review-issues" aria-labelledby={`${id}-heading`}>
      {issues.length === 0 ? (
        <p id={`${id}-heading`} className="review-done">
          אין נקודות פתוחות לבדיקה.
        </p>
      ) : (
        <>
          <h3 id={`${id}-heading`} className="section-title">
            לבדיקה ({issues.length})
          </h3>
          <p className="field-hint">השוו לטקסט המקורי, תקנו בטופס אם צריך, והחליטו על כל נקודה.</p>
          <ul className="review-list">
            {issues.map((issue, i) => (
              <ReviewPoint key={issue.key} issue={issue} form={form} index={i} onChange={onChange} />
            ))}
          </ul>
        </>
      )}
      {resolved.length > 0 && (
        <div className="review-resolved">
          <h4 className="comparison-subtitle">הוחלט בבדיקה ({resolved.length})</h4>
          <ul className="resolved-list">
            {resolved.map((entry, i) => (
              <li key={entry.key} className="resolved-item">
                <span className="resolution-label">{RESOLUTION_LABELS[entry.resolution]}</span>
                <span dir="auto" className="resolved-text">
                  {resolvedText(entry)}
                </span>
                {!entry.saved && <span className="unsaved-mark">לא נשמר עדיין</span>}
                <button type="button" className="text-button" aria-label={`ביטול: ${resolvedText(entry)}`} onClick={() => onChange(undoResolved(form, i))}>
                  ביטול
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function ReviewPoint({ issue, form, index, onChange }: { issue: IssueRow; form: RecipeForm; index: number; onChange: (form: RecipeForm) => void }) {
  const proposal = proposalOf(issue)
  const listed = proposal !== null && listsIngredient(form.ingredient_groups, proposal)
  const group = proposal === null ? -1 : targetGroup(form.ingredient_groups, proposal.group)
  return (
    <li className="review-issue">
      <div className="review-issue-text">
        <span className="issue-kind">{ISSUE_LABELS[issue.kind]}</span>
        <p dir="auto">{issue.message}</p>
        {issue.quote !== null && (
          <blockquote className="issue-quote" dir="auto">
            {issue.quote}
          </blockquote>
        )}
        {proposal !== null &&
          (listed ? (
            <p className="proposed-line">כבר יש ברשימת המצרכים שורה עם "{proposal.text}".</p>
          ) : (
            <p className="proposed-line">
              <span className="proposed-label">השורה שתתווסף:</span> <bdi>{proposal.text}</bdi> ·{' '}
              {proposal.quantity === null ? 'ללא כמות' : <>כמות: <bdi>{proposal.quantity}</bdi></>} ·{' '}
              {group >= 0 ? <>בקבוצה "<bdi>{form.ingredient_groups[group].name.trim()}</bdi>"</> : 'בלי קבוצה'}
            </p>
          ))}
      </div>
      {/* The visible words come first in each spoken name, so voice control ("click התעלמות") works. */}
      <div className="review-actions">
        {proposal !== null && !listed ? (
          <button type="button" className="button-primary" onClick={() => onChange(addProposed(form, index))}>
            הוספת {proposal.text} למצרכים
          </button>
        ) : (
          <button type="button" className="button" aria-label={`טופל: ${issue.message}`} onClick={() => onChange(resolvePoint(form, index, 'handled'))}>
            טופל
          </button>
        )}
        {proposal !== null && (
          <button type="button" className="button" aria-label={`התעלמות: ${issue.message}`} onClick={() => onChange(resolvePoint(form, index, 'dismissed'))}>
            התעלמות
          </button>
        )}
      </div>
    </li>
  )
}

/** A decision in a few words: the line that was added, or the point's message. */
function resolvedText(entry: ResolvedRow): string {
  return entry.resolution === 'added' && entry.proposed ? entry.proposed.text : entry.message
}
