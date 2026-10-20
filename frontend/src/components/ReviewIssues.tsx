import { useId } from 'react'
import { removeAt, type IssueRow } from '../editorForm'
import { ISSUE_LABELS } from '../labels'

interface ReviewIssuesProps {
  issues: IssueRow[]
  onChange: (issues: IssueRow[]) => void
}

// What the import flagged for review. Each point can be marked as handled, which removes it
// from the list; "save as draft" keeps the points still open, "save as recipe" ends the review.
export default function ReviewIssues({ issues, onChange }: ReviewIssuesProps) {
  const id = useId()
  if (issues.length === 0) {
    return <p className="review-done">אין נקודות פתוחות לבדיקה.</p>
  }
  return (
    <section className="review-issues" aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} className="section-title">
        לבדיקה ({issues.length})
      </h3>
      <p className="field-hint">השוו לטקסט המקורי, תקנו בטופס אם צריך, וסמנו כל נקודה כשטיפלתם בה.</p>
      <ul className="review-list">
        {issues.map((issue, i) => (
          <li key={issue.key} className="review-issue">
            <div className="review-issue-text">
              <span className="issue-kind">{ISSUE_LABELS[issue.kind]}</span>
              <p dir="auto">{issue.message}</p>
              {issue.quote !== null && (
                <blockquote className="issue-quote" dir="auto">
                  {issue.quote}
                </blockquote>
              )}
            </div>
            {/* The visible word comes first in the spoken name, so voice control ("click טופל") works. */}
            <button type="button" className="button" aria-label={`טופל: ${issue.message}`} onClick={() => onChange(removeAt(issues, i))}>
              טופל
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
