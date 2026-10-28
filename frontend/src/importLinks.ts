// Which importer a pasted link goes to. Today only public Instagram posts import; recipe websites
// are a later milestone, and the page says so instead of sending a link nothing can read yet.

export type LinkKind = 'empty' | 'instagram' | 'website' | 'not_a_link'

export function linkKind(text: string): LinkKind {
  const value = text.trim()
  if (value === '') return 'empty'
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return 'not_a_link'
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return 'not_a_link'
  return /(^|\.)instagram\.com$/i.test(url.hostname) ? 'instagram' : 'website'
}

/** What "ייבוא מתכון מקישור" accepts today. */
export const LINK_HELP = 'כרגע אפשר לייבא קישורים לפוסטים ולסרטוני Reels ציבוריים באינסטגרם. ייבוא מאתרי מתכונים יתווסף בהמשך.'

export const WEBSITE_NOT_YET = 'ייבוא מאתרי מתכונים עוד לא זמין. בינתיים אפשר להעתיק את המתכון מהאתר ולהדביק את הטקסט.'

export const NOT_A_LINK = 'זה לא נראה כמו קישור. קישור מתחיל ב-https://'
