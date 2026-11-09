import type { Ref } from 'react'
import type { Recipe } from '../types'

const dateFormat = new Intl.DateTimeFormat('he-IL', { dateStyle: 'long' })

const TECHNOLOGIES = ['Python', 'FastAPI', 'React', 'TypeScript', 'SQLite', 'Qwen3:8B', 'Ollama']

/** What each featured comparison shows, in this order. Each was checked against its recorded demonstration
 * (docs/public-notebook.md); a recipe not listed here is shown after these, with its title alone. */
const EXAMPLES: ReadonlyArray<[number, string]> = [
  [12, 'זיהוי מצרך חסר והוספתו במהלך הבדיקה, לצד תיקון סוג הקינוח.'],
  [15, 'חילוץ מתכון מהטקסט שנשמר מדף באתר וסיווג נכון, עם תיקון מיקום של הערת אפייה בבדיקה.'],
  [29, 'שמירת הפניה למתכון נוסף וסינון התרעות ללא בסיס בטקסט.'],
  [36, 'חילוץ קבוצות מצרכים ומספר יחידות, תוך סינון תוכן פרסומי.'],
  [38, 'חילוץ מצרכים, כמויות והערות, עם סיווג נכון וללא תיקוני תוכן בבדיקה.'],
]
const EXAMPLE_NOTES = new Map(EXAMPLES)
const EXAMPLE_ORDER = EXAMPLES.map(([id]) => id)

function inExampleOrder(recipes: Recipe[]): Recipe[] {
  const place = (recipe: Recipe) => {
    const index = EXAMPLE_ORDER.indexOf(recipe.id)
    return index === -1 ? EXAMPLE_ORDER.length : index
  }
  return [...recipes].sort((a, b) => place(a) - place(b))
}

interface AboutPageProps {
  /** The recipes that show their original text beside the saved recipe. */
  compared: Recipe[]
  exportedAt: string
  repositoryUrl: string | null
  titleRef?: Ref<HTMLHeadingElement>
  onOpenComparison: (recipeId: number) => void
}

// The public copy's page about the project, for someone deciding quickly what it is: why it exists (in the
// person's own words), what it is built with, how a recipe gets in, the main design decision, the featured
// comparisons with what each shows, how it was tested and evaluated, and what each part does. Everything is
// visible: nothing essential is folded away.
export default function AboutPage({ compared, exportedAt, repositoryUrl, titleRef, onOpenComparison }: AboutPageProps) {
  return (
    <article className="recipe-view about-page">
      <h2 ref={titleRef} className="recipe-title" tabIndex={-1}>
        על מחברת המתכונים
      </h2>

      <section className="recipe-section">
        <h3 className="section-title">הרעיון מאחורי הפרויקט</h3>
        <p>
          הפרויקט התחיל מהאהבה שלי לאפייה ומהרגל לשמור מתכונים באינסטגרם ובאתרים שונים. עם הזמן המתכונים התפזרו בין המקורות, והיה קשה למצוא
          אותם ולעקוב אחרי מה שכבר הכנתי ומה שעוד רציתי לנסות.
        </p>
        <p>
          בניתי את מחברת המתכונים כדי לרכז אותם במקום אחד, עם חיפוש, חלוקה לקטגוריות וסימון מתכונים שכבר הכנתי. המערכת נעזרת במודל שפה כדי
          להפוך טקסט מהמקור לטיוטת מתכון מסודרת, שאפשר לבדוק ולערוך לפני השמירה.
        </p>
      </section>

      <div className="about-summary">
        <ul className="tech-tags" aria-label="טכנולוגיות">
          {TECHNOLOGIES.map((name) => (
            <li key={name} dir="ltr">
              {name}
            </li>
          ))}
        </ul>
        <p>
          אפליקציה מקומית לייבוא וניהול מתכונים, המשלבת מודל שפה עם עיבוד טקסט, כללי בדיקה ועריכה לפני השמירה. האתר הציבורי הוא גרסה סטטית
          לצפייה, המתארחת ב־Cloudflare Pages.
        </p>
      </div>

      <section className="recipe-section">
        <h3 className="section-title">איך מתכון נכנס למחברת</h3>
        <ol className="process-steps">
          <li>
            <span className="process-step-title">קריאת המקור</span>
            המערכת קוראת כיתוב של פוסט ציבורי באינסטגרם, דף מתכון באתר או טקסט שהודבק ישירות. המקור נשמר לצד המתכון, כדי שאפשר יהיה לחזור
            אליו ולהשוות.
          </li>
          <li>
            <span className="process-step-title">זיהוי התוכן וסיווג</span>
            כשמעבדים טקסט, מודל השפה המקומי מזהה אילו קטעים הם מצרכים, שלבי הכנה והערות, ואילו אינם חלק מהמתכון. בבקשה נפרדת הוא מציע
            קטגוריה מתוך הקטגוריות הקיימות. באתרים עם נתוני מתכון מובנים, המערכת יכולה לחלץ את המתכון ישירות.
          </li>
          <li>
            <span className="process-step-title">בניית הטיוטה ובדיקתה</span>
            המערכת בונה את המתכון מהקטעים המקוריים ומפענחת כמויות באמצעות כללים בקוד. בדיקות נוספות יכולות להצביע על בעיות, למשל מצרך שמופיע
            בהוראות אך חסר ברשימת המצרכים.
          </li>
          <li>
            <span className="process-step-title">עריכה ושמירה</span>
            הטיוטה מוצגת לבדיקה מול המקור. אפשר לתקן את הסיווג, לערוך את התוכן ולהוסיף או לדחות מצרך שהמערכת סימנה כחסר. המתכון נשמר במחברת
            עם המקור והקרדיט ליוצר.
          </li>
        </ol>
      </section>

      <section className="recipe-section about-callout">
        <h3 className="section-title">למה המודל לא מנסח את המתכון מחדש?</h3>
        <p>
          בניסויים הראשונים, יצירה מחדש של הטקסט הובילה לשינויים במילים מהמקור. לכן עברתי לגישה שבה המודל מסמן את תפקידם של קטעים, והמערכת
          בונה מהם את הטיוטה תוך שימוש בנוסח המקורי. הגישה מצמצמת שכתוב לא רצוי, אך עדיין דורשת בדיקה של בחירת הקטעים, הכמויות והסיווג.
        </p>
      </section>

      {compared.length > 0 && (
        <section className="recipe-section">
          <h3 className="section-title">לראות את התהליך בפועל</h3>
          <p>
            בחמש הדוגמאות הבאות אפשר להשוות בין המקור, הטיוטה שהמערכת הפיקה והתוצאה לאחר הבדיקה. בכל דוגמה מוצג מה ביצע המודל, מה טופל
            באמצעות כללי המערכת ומה תוקן בבדיקה.
          </p>
          <p>הדוגמאות נבחרו כדי להמחיש יכולות שונות של המערכת; הן אינן מדגם למדידת הדיוק הכולל שלה.</p>
          <ul className="compared-list">
            {inExampleOrder(compared).map((recipe) => {
              const note = EXAMPLE_NOTES.get(recipe.id)
              return (
                <li key={recipe.id}>
                  <button
                    type="button"
                    className="text-button"
                    dir="auto"
                    aria-describedby={note ? `example-note-${recipe.id}` : undefined}
                    onClick={() => onOpenComparison(recipe.id)}
                  >
                    {recipe.title}
                  </button>
                  {note && (
                    <span id={`example-note-${recipe.id}`} className="compared-note">
                      {note}
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      )}

      <section className="recipe-section">
        <h3 className="section-title">בדיקות והערכת איכות</h3>
        <h4 className="about-subtitle">
          בדיקות תוכנה — <bdi>pytest</bdi> ו־<bdi>Vitest</bdi>
        </h4>
        <p>
          בדיקות אוטומטיות בודקות את פעולות הייבוא, השמירה והעריכה ואת התנהגות הממשק, כדי לוודא ששינויים בקוד אינם פוגעים בפעולות קיימות.
        </p>
        <h4 className="about-subtitle">הערכת איכות המודל</h4>
        <p>
          בבדיקות האיכות השוויתי את התוצאה למקור: האם נשמרו המצרכים והכמויות, האם ההוראות אורגנו נכון והאם הסיווג מתאים. שינויים בהנחיות למודל
          נבדקו מול הגרסה הקודמת, תוך מעקב גם אחרי שיפורים וגם אחרי מקרים שנפגעו.
        </p>
        <p className="about-callout about-result">
          באוסף בדיקה של 119 מקרים, מעבר לבקשת סיווג ישירה העלה את מספר המקרים שבהם הסיווג היה נכון במלואו{' '}
          <strong>מ־74 ל־86</strong>. "נכון במלואו" מתייחס לסיווג בלבד: הקטגוריה, ובקינוחים גם סוג הקינוח; לא לחילוץ המתכון כולו. הנתון
          מתייחס לאוסף שנבדק, ואינו אומדן לדיוק במתכונים חדשים. הסיווג נשאר הצעה שניתן לתקן לפני השמירה.
        </p>
      </section>

      <section className="recipe-section">
        <h3 className="section-title">מאחורי הקלעים</h3>
        <ul className="note-list about-stack">
          <li>
            <strong>
              <bdi>React</bdi> ו־<bdi>TypeScript</bdi>
            </strong>{' '}
            — הממשק: הגלריה, החיפוש, מסך הבדיקה מול המקור והעריכה.
          </li>
          <li>
            <strong>
              <bdi>FastAPI</bdi> (<bdi>Python</bdi>)
            </strong>{' '}
            — השרת המקומי: קריאת המקורות, הבקשות למודל, בניית הטיוטה ובדיקתה, והשמירה.
          </li>
          <li>
            <strong>
              <bdi>SQLite</bdi>
            </strong>{' '}
            — המחברת עצמה: המתכונים, הטקסט המקורי של כל ייבוא, הקטגוריות וסימוני המתכונים שהכנתי.
          </li>
          <li>
            <strong>
              <bdi>Qwen3:8B</bdi> דרך <bdi>Ollama</bdi>
            </strong>{' '}
            — מודל שפה קיים שרץ על המחשב שלי, ולא אומן בפרויקט. העבודה היא בשילובו באפליקציה: מה מבקשים ממנו, ואיך התשובות נבדקות לפני שהן
            הופכות לטיוטה.
          </li>
        </ul>
        <p>
          האפליקציה המקומית היא זו שמייבאת, בודקת ושומרת. האתר הזה הוא עותק שמיוצא ממנה: מבחר מתכונים שמורים וההדגמות שלהם, כקבצים סטטיים
          ב־Cloudflare Pages, בלי שרת ובלי מודל מאחוריהם.
        </p>
      </section>

      <p className="about-footer">
        עודכן ב-<time dateTime={exportedAt}>{dateFormat.format(new Date(exportedAt))}</time>.
        {repositoryUrl !== null && (
          <>
            {' '}
            הקוד והתיעוד המלא (באנגלית):{' '}
            <a href={repositoryUrl} target="_blank" rel="noopener noreferrer" dir="ltr">
              {repositoryUrl}
            </a>
          </>
        )}
      </p>
    </article>
  )
}

/** Above the public gallery, where the notebook has its import strip: a welcome. How it works is on the "about" page. */
export function PublicIntro({ onAbout }: { onAbout: () => void }) {
  return (
    <section className="public-intro" aria-label="על העותק הזה">
      <p>
        <strong>ברוכים הבאים למחברת המתכונים שלי.</strong> כאן תמצאו מתכונים שאספתי מאינסטגרם ומהרשת — חלקם כבר הכנתי, ואחרים עוד מחכים
        לתורם.
      </p>
      <button type="button" className="button" onClick={onAbout}>
        איך זה עובד
      </button>
    </section>
  )
}
