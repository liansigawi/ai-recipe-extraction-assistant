// The credit: who made a recipe, as a display name and an Instagram username. Plain functions, no React.
import type { Creator, Source } from './types'

const USERNAME = /(?:^|[\s(])@([A-Za-z0-9._]{1,30})(?=[\s)]|$)/ // also "(@user)"

export function profileUrl(username: string): string {
  return `https://www.instagram.com/${username}/`
}

/** The name worth showing beside the username: none when it only repeats it ("alehonline", "@alehonline"). */
export function shownName(creator: Creator): string | null {
  if (creator.name === null) return null
  if (creator.username !== null && creator.name.replace(/^@/, '').toLowerCase() === creator.username.toLowerCase()) return null
  return creator.name
}

/** One credit as the editor writes it: "ריטה קדוש @ritakadosh_", "@alehonline", "Example Kitchen". */
export function creatorToText(creator: Creator): string {
  return [creator.name, creator.username !== null ? `@${creator.username}` : null].filter((part) => part !== null).join(' ')
}

/** The editor's text back into credits: separated by commas; in each, "@user" is the username and the rest
 * (without parentheses) the display name. */
export function creatorsFromText(text: string): Creator[] {
  return text
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry !== '')
    .map((entry) => {
      const match = USERNAME.exec(entry)
      const rest = match !== null ? entry.replace(match[0], ' ') : entry
      const name = rest.replace(/[()]/g, ' ').replace(/\s+/g, ' ').trim()
      return { name: name === '' ? null : name, username: match !== null ? match[1] : null }
    })
}

/** The source credited under the title: the first one that names its creators. */
export function creditedSource(sources: Source[]): Source | undefined {
  return sources.find((source) => source.creators.length > 0)
}

/** The link to the original post: the credited source's, or else the first Instagram source's. */
export function postLink(sources: Source[]): Source | undefined {
  const credited = creditedSource(sources)
  if (credited?.url) return credited
  return sources.find((source) => source.kind === 'instagram' && source.url !== null) ?? sources.find((source) => source.url !== null)
}
