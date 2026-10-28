// Which picture to show for a recipe or one of its media items, and its Instagram post. No React.
import type { MediaReport, Recipe, RecipeMediaItem } from './types'

/** The picture of an item: the image itself, or a video's poster. null when there is none. */
export function pictureUrl(item: RecipeMediaItem): string | null {
  return item.kind === 'image' ? (item.file?.url ?? null) : (item.thumbnail?.url ?? null)
}

/** The item shown on the recipe's card. */
export function coverOf(recipe: Recipe): RecipeMediaItem | undefined {
  return recipe.media.find((item) => item.id === recipe.cover_id)
}

const INSTAGRAM_POST = /^https?:\/\/(?:www\.|m\.)?instagram\.com\/(?:[^/]+\/)?(?:p|reel|reels|tv)\/[A-Za-z0-9_-]+/

/** The recipe's Instagram post, for "fetch media from the post": its original's, else an Instagram source's. */
export function instagramPostOf(recipe: Recipe): string | null {
  const addresses = [recipe.original?.url ?? null, ...recipe.sources.map((source) => source.url)]
  return addresses.find((url): url is string => url !== null && INSTAGRAM_POST.test(url)) ?? null
}

/** What a fetch from the post did, in a sentence. */
export function reportText(report: MediaReport): string {
  if (report.found === 0) return 'בפוסט לא נמצאו תמונות או סרטונים.'
  const parts = [report.found === 1 ? 'בפוסט פריט אחד.' : `בפוסט ${report.found} פריטים.`]
  if (report.saved > 0) parts.push(report.saved === 1 ? 'פריט אחד נשמר עכשיו.' : `${report.saved} נשמרו עכשיו.`)
  if (report.already_had > 0) parts.push(report.already_had === 1 ? 'אחד כבר היה במתכון.' : `${report.already_had} כבר היו במתכון.`)
  if (report.thumbnails_only > 0) {
    parts.push(
      report.thumbnails_only === 1
        ? 'סרטון אחד נשמר רק כתמונה, עם קישור לצפייה בפוסט.'
        : `${report.thumbnails_only} סרטונים נשמרו רק כתמונה, עם קישור לצפייה בפוסט.`,
    )
  }
  if (report.failed > 0) parts.push(report.failed === 1 ? 'פריט אחד לא נשמר.' : `${report.failed} פריטים לא נשמרו.`)
  return parts.join(' ')
}
