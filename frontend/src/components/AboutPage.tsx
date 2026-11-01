import type { Ref } from 'react'
import type { Recipe } from '../types'

const dateFormat = new Intl.DateTimeFormat('he-IL', { dateStyle: 'long' })

interface AboutPageProps {
  /** The recipes that show their original text beside the saved recipe. */
  compared: Recipe[]
  exportedAt: string
  repositoryUrl: string | null
  titleRef?: Ref<HTMLHeadingElement>
  onOpenComparison: (recipeId: number) => void
}

// The public copy's page about the project: what it is, how a recipe gets in, how it is checked, and
// what is still an experiment. Short on purpose: the details are in the repository's README and docs.
export default function AboutPage({ compared, exportedAt, repositoryUrl, titleRef, onOpenComparison }: AboutPageProps) {
  return (
    <article className="recipe-view about-page">
      <h2 ref={titleRef} className="recipe-title" tabIndex={-1}>
        על מחברת המתכונים
      </h2>
      <p>
        פרויקט אישי: מחברת מתכונים שרצה על המחשב שלי. היא מייבאת מתכונים מפוסטים באינסטגרם, מדפי מתכונים באתרים ומטקסט שמודבק, והופכת
        אותם למתכונים מסודרים שאפשר לחפש ולסנן. הממשק כתוב ב-React וב-TypeScript, והשרת ב-Python (FastAPI) עם SQLite.
      </p>
      <p>
        זה עותק ציבורי לקריאה בלבד של מתכונים שבחרתי מהמחברת: אפשר לדפדף, לחפש ולסנן, אבל לא לשנות דבר. מאחוריו אין שרת ואין מודל, רק
        קבצים.
      </p>

      <section className="recipe-section">
        <h3 className="section-title">איך מתכון נכנס למחברת</h3>
        <ol className="process-steps">
          <li>
            <span className="process-step-title">קריאת המקור</span>
            השרת המקומי קורא את הכיתוב מהדף הציבורי של הפוסט באינסטגרם, או את המתכון מדף האתר (נתוני המתכון שבדף, או הטקסט הראשי שלו).
            הטקסט נשמר כמו שהוא, ומטופל כחומר מקור בלבד, אף פעם לא כהוראות.
          </li>
          <li>
            <span className="process-step-title">תיוג</span>
            השרת מחלק את הטקסט לקטעים ממוספרים, ומודל שפה שרץ על כרטיס המסך של המחשב הנייד שלי (<bdi>Qwen3 8B</bdi> דרך Ollama, על{' '}
            <bdi>8 GB</bdi>) מסמן לכל קטע את תפקידו: כותרת, מצרך, שלב, טיפ, או לא חלק מהמתכון. בבקשה שנייה הוא בוחר קטגוריה, רק מתוך
            הקיימות. בהגדרה אחת אפשר להחליף אותו ב-Claude API.
          </li>
          <li>
            <span className="process-step-title">בניית הטיוטה</span>
            השרת מעתיק כל מצרך וכל שלב מהטקסט עצמו, אות באות, וקורא את הכמות מכל שורה לפי כללים קבועים: המודל לא מקליד את המתכון מחדש
            ולא ממציא כמויות. מה שלא ברור, או מצרך שמופיע רק בהוראות, מסומן כנקודה לבדיקה.
          </li>
          <li>
            <span className="process-step-title">בדיקה</span>
            הטיוטה נבדקת מול הטקסט המקורי, מתוקנת ונשמרת. רק מתכונים שנשמרו מופיעים כאן.
          </li>
        </ol>
        <p>
          למה להעתיק ולא להקליד מחדש? בגרסה הראשונה המודל הקליד את המתכון מחדש, והחליף מילים נדירות במילים דומות: "מג׳הול" הפך ל-"
          <bdi>מג׳ hollow</bdi>". הבעיה הייתה בעצם ההקלדה ולא בהגדרה כלשהי, ולכן מאז המודל רק מסמן תפקידים.
        </p>
      </section>

      {compared.length > 0 && (
        <section className="recipe-section">
          <h3 className="section-title">מהמקור למתכון</h3>
          <p>בכמה מתכונים אפשר לראות את הטקסט המקורי לצד המתכון השמור, ומה ידוע על הדרך ביניהם:</p>
          <ul className="compared-list">
            {compared.map((recipe) => (
              <li key={recipe.id}>
                <button type="button" className="text-button" dir="auto" onClick={() => onOpenComparison(recipe.id)}>
                  {recipe.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="recipe-section">
        <h3 className="section-title">בדיקות</h3>
        <ul className="note-list">
          <li>בדיקות תוכנה אוטומטיות לשרת ולממשק (pytest ו-Vitest), שרצות בלי מודל ובלי אינטרנט.</li>
          <li>
            בדיקת איכות נפרדת מריצה את המודל האמיתי על 37 מתכוני בדיקה שנכתבו לשם כך ועל כיתובים אמיתיים, ומשווה כל טיוטה לציפיות שנכתבו
            ביד: מילים שהשתנו, שורות חסרות או מיותרות, כמויות, קבוצות, קטגוריה ונקודות לבדיקה. התוצאות מתועדות, כולל מה שעדיין נכשל.
          </li>
        </ul>
      </section>

      <section className="recipe-section">
        <h3 className="section-title">בניסוי: ייבוא מצילומי מסך</h3>
        <p>
          ייבוא מתכון מצילום מסך עדיין לא חלק מהמחברת. נבדקו כמה דרכים מקומיות לקרוא צילומי מסך אמיתיים של מתכונים בעברית; הטובה שבהן
          קוראת נכון את רוב המילים, אבל עדיין משנה לפעמים מספרים, כמו כמויות וזמנים, בלי שום סימן. לכן הניסוי נמשך, והייבוא מצילומי מסך לא
          שוחרר.
        </p>
      </section>

      <section className="recipe-section">
        <h3 className="section-title">העותק הזה</h3>
        <p>
          נוצר מהמחברת בסקריפט ייצוא: רק מתכונים שמורים שבחרתי, ורק מה שהעמודים מציגים. לכל מתכון נשמרים הקרדיט ליוצרים והקישור למקור;
          מסרטונים מוצגת רק תמונה, עם קישור לפוסט. עודכן ב-<time dateTime={exportedAt}>{dateFormat.format(new Date(exportedAt))}</time>.
        </p>
        {repositoryUrl !== null && (
          <p>
            הקוד והתיעוד המלא (באנגלית):{' '}
            <a href={repositoryUrl} target="_blank" rel="noopener noreferrer" dir="ltr">
              {repositoryUrl}
            </a>
          </p>
        )}
      </section>
    </article>
  )
}

/** Above the public gallery, where the notebook has its import strip: what this is, in a sentence. */
export function PublicIntro({ onAbout }: { onAbout: () => void }) {
  return (
    <section className="public-intro" aria-label="על העותק הזה">
      <p>
        <strong>עותק ציבורי לקריאה בלבד של מחברת המתכונים שלי.</strong> מתכונים שיובאו מאינסטגרם, מאתרים ומטקסט, עובדו לטיוטה על ידי מודל
        שפה שרץ על המחשב שלי, ונבדקו ביד לפני שנשמרו.
      </p>
      <button type="button" className="button" onClick={onAbout}>
        איך זה עובד
      </button>
    </section>
  )
}
