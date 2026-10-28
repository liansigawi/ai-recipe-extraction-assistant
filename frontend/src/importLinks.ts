// What a pasted link is, for the page's own checks and messages. The backend chooses the importer by
// the host name (POST /api/imports/link): Instagram's for a post or Reel, the website importer for any
// other page.

export type LinkKind = 'empty' | 'instagram' | 'website' | 'not_a_link'

export function linkKind(text: string): LinkKind {
  const value = text.trim()
  if (value === '') return 'empty'
  // "example.com/cake", pasted without https://, is a link too (the backend adds it).
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(value) || !/^[^\s/]+\.[^\s/]+/.test(value) ? value : `https://${value}`
  let url: URL
  try {
    url = new URL(withScheme)
  } catch {
    return 'not_a_link'
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return 'not_a_link'
  return /(^|\.)instagram\.com$/i.test(url.hostname) ? 'instagram' : 'website'
}

/** What "ייבוא מתכון מקישור" accepts. */
export const LINK_HELP =
  'אפשר לייבא פוסטים וסרטוני Reels ציבוריים מאינסטגרם, ודפי מתכונים מאתרים. לא כל אתר נקרא: אם דף לא נקרא, אפשר להדביק את טקסט המתכון.'

export const NOT_A_LINK = 'זה לא נראה כמו קישור. קישור מתחיל ב-https://'
