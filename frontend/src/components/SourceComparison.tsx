import { Fragment, useId, type Ref } from 'react'
import { ISSUE_LABELS, RESOLUTION_LABELS } from '../labels'
import { decisionFor, demonstrationSummary, elapsedText, reviewChanges, SUMMARY_TAGS, type Reviewed } from '../processing'
import type { Category, Demonstration, ImportedOriginal, Issue, KeptDraft, Recipe, ResolvedIssue } from '../types'
import CategoryChip from './CategoryChip'
import Icon from './Icon'
import { CreatorName, IngredientGroups, StepGroups } from './RecipeView'

const dateFormat = new Intl.DateTimeFormat('he-IL', { dateStyle: 'long' })
const formatDate = (iso: string) => dateFormat.format(new Date(iso))

interface SourceComparisonProps {
  recipe: Recipe
  /** The copy's categories: a dessert's subcategory is called its type. */
  categories: Category[]
  titleRef?: Ref<HTMLHeadingElement>
  onBack: () => void
}

// The public copy: one recipe beside the text it was imported from, and what the records say about the
// steps between them. Everything here comes from what was kept (the original, the saved recipe, a draft
// only when a backup held one, and a demonstration only as it was recorded); nothing is rebuilt. Review
// decisions are shown as records, never as buttons: the copy is read-only. A recipe with a recorded
// demonstration shows that demonstration as its comparison; the others, the saved recipe.
export default function SourceComparison({ recipe, categories, titleRef, onBack }: SourceComparisonProps) {
  const original = recipe.original
  if (original === null || !recipe.processing) return null
  return (
    <article className="recipe-view source-comparison">
      <div className="page-toolbar">
        <button type="button" className="back-button" onClick={onBack}>
          <Icon name="back" />
          חזרה למתכון
        </button>
      </div>
      <p className="eyebrow">מהמקור למתכון</p>
      <h2 ref={titleRef} className="recipe-title" dir="auto" tabIndex={-1}>
        {recipe.title}
      </h2>
      {recipe.processing.demonstration ? (
        <DemonstrationView
          demonstration={recipe.processing.demonstration}
          original={original}
          historicalKept={recipe.processing.draft !== null}
          categories={categories}
        />
      ) : (
        <SavedComparison recipe={recipe} original={original} draft={recipe.processing.draft} />
      )}
    </article>
  )
}

/** Where the text came from: "כיתוב של פוסט באינסטגרם מאת ...", "דף מתכון באתר ...", "טקסט שהודבק". */
function SourceSummary({ original }: { original: ImportedOriginal }) {
  const link = original.url !== null && /^https?:\/\//.test(original.url) ? original.url : null
  const people = original.author !== null ? [original.author, ...original.coauthors] : []
  // A site credited as its own author ("באתר עדיקוש מאת עדיקוש") is named once.
  const onlyTheSite = people.length === 1 && people[0].username === null && people[0].name === original.site_name
  const byline = people.length > 0 && !onlyTheSite && (
    <>
      {' מאת '}
      {people.map((person, index) => (
        <Fragment key={index}>
          {index > 0 && ', '}
          <CreatorName creator={person} />
        </Fragment>
      ))}
    </>
  )
  if (original.kind === 'instagram') {
    return (
      <span>
        כיתוב של פוסט באינסטגרם{byline}, שנקרא מ{original.retrieved_from === 'embed_view' ? 'תצוגת ההטמעה הציבורית' : 'הדף הציבורי'} של
        הפוסט.{' '}
        {link !== null && (
          <a href={link} target="_blank" rel="noopener noreferrer">
            לפוסט המקורי
          </a>
        )}
      </span>
    )
  }
  if (original.kind === 'website') {
    const structured = original.retrieved_from === 'json_ld' || original.retrieved_from === 'microdata'
    return (
      <span>
        דף מתכון
        {original.site_name && (
          <>
            {' '}
            באתר <bdi>{original.site_name}</bdi>
          </>
        )}
        {byline}: {structured ? 'נתוני המתכון שבדף' : 'הטקסט הראשי של הדף'}.{' '}
        {link !== null && (
          <a href={link} target="_blank" rel="noopener noreferrer">
            לדף המתכון
          </a>
        )}
      </span>
    )
  }
  return (
    <span>
      טקסט שהודבק ביד
      {link !== null ? (
        <>
          {' '}
          מ:{' '}
          <a href={link} target="_blank" rel="noopener noreferrer" dir="ltr">
            {link}
          </a>
        </>
      ) : (
        ', בלי קישור למקור.'
      )}
    </span>
  )
}

// No parentheses around the English names: beside Hebrew, the browser may draw them facing the wrong way.
const whereModelRuns = (model: string) => (model.startsWith('claude') ? 'מודל שנקרא דרך Claude API' : 'מודל שרץ על המחשב שלי דרך Ollama')

/** Who read it: the model, and where it ran (a local model through Ollama, or the Claude API). */
function ModelSummary({ original }: { original: ImportedOriginal }) {
  if (original.model === null) return <span>נשמר בלי עיבוד, והמתכון מולא ביד.</span>
  const where = whereModelRuns(original.model)
  if (original.retrieved_from === 'json_ld' || original.retrieved_from === 'microdata') {
    return (
      <span>
        המצרכים והשלבים הועתקו מנתוני המתכון שבדף; <bdi>{original.model}</bdi>, {where}, בחר רק קטגוריה.
      </span>
    )
  }
  return (
    <span>
      <bdi>{original.model}</bdi>, {where}, הפך את הטקסט לטיוטה ב-{formatDate(original.imported_at)}.
    </span>
  )
}

/** The draft a backup kept: the review points it raised, and what review changed, part by part. */
function DraftRecord({ draft, recipe }: { draft: KeptDraft; recipe: Recipe }) {
  return (
    <>
      <p>
        הייבוא שמר את הטיוטה ב-{formatDate(draft.saved_at)}. עותק שלה מלפני כל בדיקה נשאר בגיבוי של בסיס הנתונים, ולכן אפשר להשוות
        אותה למתכון השמור.
      </p>
      <PointList issues={draft.issues} />
      <ChangeList draft={draft} after={recipe} title="מה השתנה בבדיקה" same="ללא שינוי" />
    </>
  )
}

/** The review points a draft raised; with a review's record, what was decided about each (as text). */
function PointList({ issues, resolved }: { issues: Issue[]; resolved?: ResolvedIssue[] }) {
  if (issues.length === 0) return null
  return (
    <>
      <h4 className="comparison-subtitle">נקודות לבדיקה שהייבוא סימן ({issues.length})</h4>
      <ul className="review-list">
        {issues.map((issue, index) => {
          const decision = resolved === undefined ? undefined : decisionFor(issue, resolved)
          return (
            <li key={index} className="review-issue">
              <div className="review-issue-text">
                <span className="issue-kind">{ISSUE_LABELS[issue.kind]}</span>
                <p dir="auto">{issue.message}</p>
                {issue.quote !== null && (
                  <blockquote className="issue-quote" dir="auto">
                    {issue.quote}
                  </blockquote>
                )}
                {decision !== undefined && <Decision decision={decision} />}
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}

/** What review decided about a point, as text: for an addition, the line as it was added. */
function Decision({ decision }: { decision: ResolvedIssue | null }) {
  if (decision === null) return <p className="point-decision">לא הוחלט עליה בבדיקה.</p>
  const added = decision.resolution === 'added' ? decision.proposed : null
  return (
    <p className="point-decision">
      <span className="resolution-label">בבדיקה שבוצעה בעת הכנת ההדגמה: {RESOLUTION_LABELS[decision.resolution]}</span>
      {added && (
        <>
          {' '}
          — <bdi>{added.text}</bdi>, {added.quantity === null ? 'ללא כמות' : <>כמות: <bdi>{added.quantity}</bdi></>},{' '}
          {added.group === null ? 'בלי קבוצה' : <>בקבוצה "<bdi>{added.group}</bdi>"</>}
        </>
      )}
    </p>
  )
}

/** What review changed, part by part, and the parts it left as they were. */
function ChangeList({ draft, after, title, same }: { draft: KeptDraft; after: Reviewed; title: string; same: string }) {
  const { changed, unchanged } = reviewChanges(draft, after)
  return (
    <>
      <h4 className="comparison-subtitle">{title}</h4>
      {changed.length === 0 ? (
        <p>שום דבר בתוכן: המתכון נשמר כמו שהטיוטה הייתה.</p>
      ) : (
        <dl className="change-list">
          {changed.map((change) => (
            <Fragment key={change.part}>
              <dt>{change.part}</dt>
              <dd>
                <ul className="diff-lines" dir="auto">
                  {change.lines.map((line, index) => (
                    <li key={index} className={`diff-${line.kind}`}>
                      <span className="visually-hidden">{line.kind === 'removed' ? 'בטיוטה: ' : 'אחרי הבדיקה: '}</span>
                      {line.text}
                    </li>
                  ))}
                </ul>
              </dd>
            </Fragment>
          ))}
        </dl>
      )}
      {unchanged.length > 0 && <p className="field-hint">{same}: {unchanged.join(', ')}.</p>}
    </>
  )
}

/** The saved recipe beside its original, the steps between them, and the import's draft if a backup kept it. */
function SavedComparison({ recipe, original, draft }: { recipe: Recipe; original: ImportedOriginal; draft: KeptDraft | null }) {
  const id = useId()
  return (
    <>
      <ol className="process-steps">
        <li>
          <span className="process-step-title">המקור</span>
          <SourceSummary original={original} />
        </li>
        <li>
          <span className="process-step-title">העיבוד</span>
          <ModelSummary original={original} />
        </li>
        <li>
          <span className="process-step-title">הבדיקה</span>
          נבדק ונשמר כמתכון. נשמר לאחרונה {elapsedText(original.imported_at, recipe.updated_at)} אחרי הייבוא, ב-
          {formatDate(recipe.updated_at)}.
        </li>
      </ol>

      <div className="comparison">
        <section className="comparison-pane" aria-labelledby={`${id}-original`}>
          <h3 id={`${id}-original`} className="section-title">
            הטקסט המקורי
          </h3>
          <p className="field-hint">כפי שנקרא מהמקור, בלי שום שינוי.</p>
          {/* white-space: pre-wrap (index.css) keeps the line breaks exactly as they were. */}
          <div className="original-text-body comparison-original" dir="auto">
            {original.text}
          </div>
        </section>
        <section className="comparison-pane" aria-labelledby={`${id}-saved`}>
          <h3 id={`${id}-saved`} className="section-title">
            המתכון השמור
          </h3>
          <p className="field-hint">
            אחרי הבדיקה. <mark className="quantity-mark">מסומנת</mark> הכמות שהשרת קרא מכל שורת מצרך.
          </p>
          <RecipeBody recipe={recipe} />
        </section>
      </div>

      <section className="recipe-section draft-record" aria-labelledby={`${id}-draft`}>
        <h3 id={`${id}-draft`} className="section-title">
          הטיוטה של הייבוא, ומה השתנה בבדיקה
        </h3>
        {draft === null ? (
          <p>הטיוטה של הייבוא המקורי לא נשמרה.</p>
        ) : (
          <DraftRecord draft={draft} recipe={recipe} />
        )}
      </section>
    </>
  )
}

/** A recipe's ingredients, steps and notes, with its category, as the comparison panes show them. */
function RecipeBody({ recipe, explainAdded = false }: { recipe: Omit<Reviewed, 'title' | 'healthy'>; explainAdded?: boolean }) {
  return (
    <>
      <ul className="recipe-facts">
        <li>
          <CategoryChip category={recipe.category} subcategory={recipe.subcategory} />
        </li>
        {recipe.servings !== null && <li dir="auto">{recipe.servings}</li>}
      </ul>
      <h4 className="comparison-subtitle">מצרכים</h4>
      <IngredientGroups groups={recipe.ingredient_groups} markQuantities explainAdded={explainAdded} />
      <h4 className="comparison-subtitle">אופן ההכנה</h4>
      <StepGroups groups={recipe.step_groups} />
      {recipe.notes.length > 0 && (
        <>
          <h4 className="comparison-subtitle">הערות</h4>
          <ul className="note-list" dir="auto">
            {recipe.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

/** The recipe's original imported again with the current system, on a separate copy of the notebook, as recorded:
 * what happened (who did what), the original beside the reviewed result, and the draft from before the review, folded.
 * Never presented as the first import, and never in place of the saved recipe. */
function DemonstrationView({
  demonstration,
  original,
  historicalKept,
  categories,
}: {
  demonstration: Demonstration
  original: ImportedOriginal
  /** A backup kept the original import's own draft: it is not this one, and is not shown here. */
  historicalKept: boolean
  categories: Category[]
}) {
  const id = useId()
  const { draft, reviewed } = demonstration
  const { items, unchanged } = demonstrationSummary(demonstration, categories)
  return (
    <>
      <p className="demonstration-lead">הדגמה של ייבוא מחדש באמצעות הגרסה המעודכנת של המערכת.</p>
      <p className="demonstration-meta">
        {formatDate(demonstration.run_at)} · <bdi>{demonstration.model}</bdi>, {whereModelRuns(demonstration.model)} · בעותק נפרד של
        המחברת. הטיוטה של הייבוא המקורי, מ-{formatDate(original.imported_at)}, {historicalKept ? 'שמורה בנפרד ואינה מוצגת כאן' : 'לא נשמרה'}; המתכון
        השמור לא הוחלף בתוצאת ההדגמה.
      </p>

      <section className="recipe-section" aria-labelledby={`${id}-summary`}>
        <h3 id={`${id}-summary`} className="section-title">
          מה קרה בהדגמה הזו
        </h3>
        <p className="field-hint">מה עשתה המערכת בעצמה, ומה הוחלט בבדיקה שבוצעה בעת הכנת ההדגמה.</p>
        <ul className="summary-list">
          {items.map((item, index) => (
            <li key={index} className="summary-item">
              <p className="summary-head">
                <span className="summary-topic" dir="auto">
                  {item.topic}
                </span>
                {item.tags.map((tag) => (
                  <span key={tag} className={`summary-tag summary-tag-${tag}`}>
                    {SUMMARY_TAGS[tag]}
                  </span>
                ))}
              </p>
              <p dir="auto">{item.text}</p>
            </li>
          ))}
        </ul>
        {unchanged.length > 0 && <p className="field-hint">בלי תיקון בבדיקה: {unchanged.join(', ')}.</p>}
      </section>

      <div className="comparison">
        <section className="comparison-pane" aria-labelledby={`${id}-original`}>
          <h3 id={`${id}-original`} className="section-title">
            הטקסט המקורי
          </h3>
          <p className="field-hint">
            כפי שנקרא מהמקור, בלי שום שינוי: <SourceSummary original={original} />
          </p>
          <div className="original-text-body comparison-original" dir="auto">
            {original.text}
          </div>
        </section>
        <section className="comparison-pane" aria-labelledby={`${id}-reviewed`}>
          <h3 id={`${id}-reviewed`} className="section-title">
            המתכון לאחר הבדיקה
          </h3>
          <p className="field-hint">
            התוצאה של ההדגמה, אחרי הבדיקה. <mark className="quantity-mark">מסומנת</mark> הכמות שהשרת קרא מכל שורת מצרך.
          </p>
          <RecipeBody recipe={reviewed} explainAdded />
        </section>
      </div>

      <details className="draft-details">
        <summary>הצגת הטיוטה לפני הבדיקה</summary>
        <p>כפי שהייבוא שמר אותה ב-{formatDate(draft.saved_at)}, לפני כל בדיקה, עם הנקודות שסימן ומה שנעשה בבדיקה.</p>
        <div className="demonstration-draft">
          <RecipeBody recipe={draft} />
        </div>
        {draft.issues.length === 0 ? (
          <p className="field-hint">הייבוא לא סימן נקודות לבדיקה.</p>
        ) : (
          <PointList issues={draft.issues} resolved={reviewed.resolved_issues} />
        )}
        <ChangeList draft={draft} after={reviewed} title="מה שונה בבדיקה" same="בלי תיקון" />
      </details>
    </>
  )
}
