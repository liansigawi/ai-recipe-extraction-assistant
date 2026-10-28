import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { coverOf, instagramPostOf, pictureUrl, reportText } from './media'
import { POST_MEDIA, fakeApi, fileRef, mediaItem } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { Recipe } from './types'

// Pictures and videos, against the fake backend: the cake came from a mixed carousel (a saved video,
// an image, and a video kept only as its poster); the other recipes have no media yet.
const POST = 'https://www.instagram.com/p/CLJ5G9rDi1a/'
const [cake, soup, ...others] = sampleRecipes
const withMedia: Recipe = {
  ...cake,
  sources: [{ kind: 'instagram', url: POST, creators: [{ name: null, username: 'baker' }] }],
  media: [
    mediaItem(11, { kind: 'video', file: fileRef(111, 'video/mp4'), thumbnail: fileRef(112, 'image/jpeg'), post_index: 0 }),
    mediaItem(12, { file: fileRef(121, 'image/jpeg'), post_index: 1 }),
    mediaItem(13, { kind: 'video', status: 'thumbnail_only', file: null, thumbnail: fileRef(131, 'image/jpeg'), post_index: 2 }),
  ],
  cover_id: 11, // nothing chosen: the first item with a picture (the video's poster)
}
const fromInstagram: Recipe = { ...soup, sources: [{ kind: 'instagram', url: 'https://www.instagram.com/reel/Cm1mCdCpSzJ/', creators: [] }] }

/** The app on the recipes' gallery. */
async function renderGallery(recipes: Recipe[] = [withMedia, fromInstagram, ...others], options: Parameters<typeof userEvent.setup>[0] = {}) {
  const user = userEvent.setup(options)
  const api = fakeApi({ recipes, categories: sampleCategories })
  render(<App />)
  await screen.findByRole('region', { name: 'המתכונים' })
  return { user, api }
}

/** The app with the first recipe open. */
async function renderApp(recipes: Recipe[] = [withMedia, fromInstagram, ...others], options: Parameters<typeof userEvent.setup>[0] = {}) {
  const { user, api } = await renderGallery(recipes, options)
  await user.click(card(recipes[0].title))
  await screen.findByRole('heading', { level: 2, name: recipes[0].title })
  return { user, api }
}

// The recipe's own media; and the gallery of recipe cards (on the home page).
const gallery = () => screen.getByRole('region', { name: 'תמונות וסרטונים' })
const thumbnails = () => within(gallery()).queryAllByRole('button', { name: /מתוך/ })
const card = (title: string) => within(screen.getByRole('region', { name: 'המתכונים' })).getByRole('button', { name: new RegExp(title) })
const cardCover = (title: string) => card(title).querySelector('.recipe-card-photo img, .recipe-card-photo .placeholder')
async function backToGallery(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: 'כל המתכונים' }))
}

describe('media helpers', () => {
  it('a video shows its poster; the cover is the recipe cover_id; the post is the Instagram source', () => {
    expect(pictureUrl(withMedia.media[0])).toBe('/api/media/112')
    expect(pictureUrl(withMedia.media[1])).toBe('/api/media/121')
    expect(pictureUrl(mediaItem(1, { kind: 'video', file: fileRef(5, 'video/mp4'), thumbnail: null }))).toBeNull()
    expect(coverOf(withMedia)?.id).toBe(11)
    expect(coverOf(soup)).toBeUndefined()
    expect(instagramPostOf(withMedia)).toBe(POST)
    expect(instagramPostOf(soup)).toBeNull() // a website source
  })

  it('a fetch report says what was saved, in Hebrew grammar', () => {
    const report = { found: 1, saved: 1, thumbnails_only: 0, failed: 0, already_had: 0, problems: [] }
    expect(reportText(report)).toBe('בפוסט פריט אחד. פריט אחד נשמר עכשיו.')
    expect(reportText({ ...report, found: 4, saved: 0, thumbnails_only: 2, failed: 1, already_had: 1 })).toBe(
      'בפוסט 4 פריטים. אחד כבר היה במתכון. 2 סרטונים נשמרו רק כתמונה, עם קישור לצפייה בפוסט. פריט אחד לא נשמר.',
    )
    expect(reportText({ ...report, found: 0, saved: 0 })).toBe('בפוסט לא נמצאו תמונות או סרטונים.')
  })
})

describe('pictures and videos of a recipe', () => {
  it('the card shows the cover, and a placeholder when there is none', async () => {
    await renderGallery()
    expect(cardCover(withMedia.title)).toHaveAttribute('src', '/api/media/112')
    expect(cardCover(fromInstagram.title)).toHaveClass('placeholder') // the category's drawing
  })

  it('the gallery keeps the post order and tells a saved video from one only on Instagram', async () => {
    await renderApp()
    expect(thumbnails().map((button) => button.getAttribute('aria-label'))).toEqual([
      'סרטון 1 מתוך 3, התמונה הראשית',
      'תמונה 2 מתוך 3',
      'סרטון שלא נשמר במחשב 3 מתוך 3',
    ])
    expect(within(thumbnails()[0]).getByText('▶ סרטון')).toBeInTheDocument()
    expect(within(thumbnails()[0]).getByText('ראשית')).toBeInTheDocument()
    expect(within(thumbnails()[2]).getByText('▶ באינסטגרם בלבד')).toHaveClass('media-badge-remote')
  })

  it('the viewer enlarges a picture, plays a saved video only with its controls, and links a video that was not saved', async () => {
    const { user } = await renderApp()
    await user.click(thumbnails()[1])
    const viewer = screen.getByRole('dialog')
    expect(within(viewer).getByRole('img', { name: `תמונה 2 של ${withMedia.title}` })).toHaveAttribute('src', '/api/media/121')

    await user.click(within(viewer).getByRole('button', { name: 'הקודם' }))
    const video = viewer.querySelector('video')
    expect(video).toHaveAttribute('src', '/api/media/111')
    expect(video).toHaveAttribute('poster', '/api/media/112')
    expect(video).toHaveAttribute('controls')
    expect(video).not.toHaveAttribute('autoplay')
    expect(video).toHaveAttribute('preload', 'metadata')

    fireEvent.keyDown(viewer, { key: 'ArrowLeft' }) // right to left: the next one
    fireEvent.keyDown(viewer, { key: 'ArrowLeft' })
    expect(viewer.querySelector('video')).toBeNull()
    expect(within(viewer).getByText(/הסרטון עצמו לא נשמר במחשב הזה/)).toBeInTheDocument()
    expect(within(viewer).getByRole('link', { name: 'לצפייה בסרטון בפוסט באינסטגרם' })).toHaveAttribute('href', POST)

    await user.click(within(viewer).getByRole('button', { name: 'סגירה' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('choosing the cover changes the card, and clearing it goes back to the first picture', async () => {
    const { user, api } = await renderApp()
    await user.click(thumbnails()[0]) // the cover by default: nothing to choose or clear
    expect(within(screen.getByRole('dialog')).queryByRole('button', { name: /כתמונה ראשית/ })).not.toBeInTheDocument()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'סגירה' }))
    await user.click(thumbnails()[2])
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'קביעה כתמונה ראשית' }))
    expect(api.changes().at(-1)).toEqual({ method: 'PUT', path: `/api/recipes/${withMedia.id}/cover`, body: { media_id: 13 } })
    expect(await within(gallery()).findByText('התמונה הראשית נבחרה.')).toBeInTheDocument()
    expect(within(thumbnails()[2]).getByText('ראשית')).toBeInTheDocument()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'סגירה' }))
    await backToGallery(user)
    expect(cardCover(withMedia.title)).toHaveAttribute('src', '/api/media/131') // a video's poster can be the cover

    await user.click(card(withMedia.title))
    await user.click(thumbnails()[2])
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'ביטול הבחירה כתמונה ראשית' }))
    expect(api.changes().at(-1)?.body).toEqual({ media_id: null })
    expect(await within(gallery()).findByText('התמונה הראשית תהיה הראשונה בגלריה.')).toBeInTheDocument()
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'סגירה' }))
    await backToGallery(user)
    expect(cardCover(withMedia.title)).toHaveAttribute('src', '/api/media/112')
  })

  it('removing asks first, and only then removes the item', async () => {
    const { user, api } = await renderApp()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    await user.click(thumbnails()[1])
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'הסרה מהמתכון' }))
    expect(api.changes()).toEqual([])
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'הסרה מהמתכון' }))
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(api.changes()).toEqual([{ method: 'DELETE', path: `/api/recipes/${withMedia.id}/media/12`, body: undefined }])
    expect(await within(gallery()).findByText('הפריט הוסר מהמתכון.')).toBeInTheDocument()
    expect(thumbnails()).toHaveLength(2)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('uploads a picture to a recipe without any Instagram link', async () => {
    const { user, api } = await renderApp([soup, ...others])
    expect(within(gallery()).getByText('אין עדיין תמונות או סרטונים.')).toBeInTheDocument()
    expect(within(gallery()).queryByRole('button', { name: 'שליפת מדיה מהפוסט' })).not.toBeInTheDocument()
    await user.upload(within(gallery()).getByLabelText('העלאת תמונה'), new File(['png'], 'pita.png', { type: 'image/png' }))
    expect(api.changes()).toEqual([{ method: 'POST', path: `/api/recipes/${soup.id}/media`, body: undefined }])
    const [, init] = vi.mocked(fetch).mock.calls.at(-1) ?? []
    expect(new Headers(init?.headers).get('Content-Type')).toBe('image/png') // the file itself is the body
    expect(await within(gallery()).findByText('התמונה נוספה.')).toBeInTheDocument()
    expect(thumbnails()).toHaveLength(1)
    await backToGallery(user)
    expect(cardCover(soup.title)?.tagName).toBe('IMG')
  })

  it('refuses a file that is not a picture before sending it', async () => {
    const { user, api } = await renderApp([soup, ...others], { applyAccept: false })
    await user.upload(within(gallery()).getByLabelText('העלאת תמונה'), new File(['%PDF'], 'menu.pdf', { type: 'application/pdf' }))
    expect(within(gallery()).getByRole('alert')).toHaveTextContent('"menu.pdf" אינה תמונה מסוג JPEG, PNG, WebP או GIF.')
    expect(api.changes()).toEqual([])
  })

  it('fetches an existing recipe’s media from its post, reports what was saved, and adds nothing twice', async () => {
    const { user, api } = await renderApp([fromInstagram, ...others])
    await user.click(within(gallery()).getByRole('button', { name: 'שליפת מדיה מהפוסט' }))
    expect(api.changes()).toEqual([{ method: 'POST', path: `/api/recipes/${fromInstagram.id}/media/instagram`, body: {} }])
    expect(await within(gallery()).findByText('בפוסט 3 פריטים. 2 נשמרו עכשיו. סרטון אחד נשמר רק כתמונה, עם קישור לצפייה בפוסט.')).toBeInTheDocument()
    expect(within(gallery()).getByText(/גדול מדי/)).toBeInTheDocument() // in the details
    expect(thumbnails()).toHaveLength(POST_MEDIA.length)
    expect(screen.getByRole('heading', { level: 2, name: fromInstagram.title })).toBeInTheDocument() // the recipe itself is as it was

    await user.click(within(gallery()).getByRole('button', { name: 'שליפת מדיה מהפוסט' }))
    expect(await within(gallery()).findByText('בפוסט 3 פריטים. 3 כבר היו במתכון.')).toBeInTheDocument()
    expect(thumbnails()).toHaveLength(POST_MEDIA.length)
  })

  it('says why a fetch failed', async () => {
    const { user, api } = await renderApp([fromInstagram, ...others])
    api.answerNextWith(502, { error: { code: 'instagram_unavailable', message: 'Unavailable.', details: null } })
    await user.click(within(gallery()).getByRole('button', { name: 'שליפת מדיה מהפוסט' }))
    expect(await within(gallery()).findByRole('alert')).not.toBeEmptyDOMElement()
    expect(thumbnails()).toHaveLength(0)
  })

  it('the review screen of an imported post shows what was saved from it, without changing anything', async () => {
    const user = userEvent.setup()
    const media = POST_MEDIA.map((item, index) => ({ ...item, id: 70 + index }))
    fakeApi({ recipes: [soup], categories: sampleCategories, draftFor: () => ({ title: 'עוגיות', media, cover_id: 70 }) })
    render(<App />)
    const strip = within(await screen.findByRole('region', { name: 'ייבוא מתכון מקישור' }))
    await user.type(strip.getByLabelText('קישור למתכון'), POST)
    await user.click(strip.getByRole('button', { name: 'ייבוא' }))
    expect(await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })).toBeInTheDocument()
    expect(thumbnails()).toHaveLength(3)
    expect(within(gallery()).queryByLabelText('העלאת תמונה')).not.toBeInTheDocument()
    await user.click(thumbnails()[1])
    const viewer = screen.getByRole('dialog')
    expect(within(viewer).queryByRole('button', { name: 'קביעה כתמונה ראשית' })).not.toBeInTheDocument()
    expect(within(viewer).queryByRole('button', { name: 'הסרה מהמתכון' })).not.toBeInTheDocument()
  })

  it('a picture whose file is missing says so in its place', async () => {
    await renderApp()
    const image = thumbnails()[1].querySelector('img')
    expect(image).not.toBeNull()
    fireEvent.error(image as HTMLImageElement)
    expect(within(thumbnails()[1]).getByText('התמונה לא נמצאה')).toBeInTheDocument()
  })
})
