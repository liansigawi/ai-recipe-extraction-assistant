import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { AMBIGUOUS, INSTAGRAM_CAPTION, fakeApi, type DraftMaker } from './test/fakeApi'
import { sampleCategories, sampleRecipes } from './test/sampleRecipes'
import type { ExtractionInfo } from './types'

// Importing pasted text, reviewing the draft, and saving it, against the fake backend.
// The fake import turns the text into a draft: its first line is the title, its second an
// ingredient, with two points to check (see test/fakeApi.ts).

const PASTED = 'עוגת תפוזים\n200 גרם קמח\nמערבבים ואופים.'

const CLAUDE: ExtractionInfo = { configured: true, provider: 'claude', model: 'claude-opus-5-5', local: false, problem: null }
const NO_KEY: ExtractionInfo = { ...CLAUDE, configured: false, problem: 'no_api_key' }
const LOCAL: ExtractionInfo = { configured: true, provider: 'ollama', model: 'qwen3:8b', local: true, problem: null }

async function openImport(options: { configured?: boolean; extraction?: ExtractionInfo; draftFor?: DraftMaker } = {}) {
  const user = userEvent.setup()
  const extraction = options.extraction ?? (options.configured === false ? NO_KEY : CLAUDE)
  const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories, extraction, draftFor: options.draftFor })
  const view = render(<App />)
  // From the gallery's import strip: "אפשר גם להדביק טקסט של מתכון".
  await user.click(await screen.findByRole('button', { name: 'להדביק טקסט של מתכון' }))
  // Wait until the panel knows whether and how the model can be used.
  await screen.findByText(
    !extraction.configured ? /אפשר לשמור את הטקסט בלי עיבוד/ : extraction.local ? /ולא נשלח לשום מקום/ : /נשלחים ל-Anthropic/,
  )
  return { user, api, view }
}

const textBox = () => screen.getByLabelText('טקסט המתכון')
const linkBox = () => screen.getByLabelText('קישור למתכון')

async function importPasted(user: ReturnType<typeof userEvent.setup>) {
  await user.click(textBox())
  await user.paste(PASTED)
  await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
  await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
}

describe('importing pasted text', () => {
  it('sends the text, then opens the draft for review beside the original', async () => {
    const { user, api } = await openImport()
    expect(textBox()).toHaveFocus() // opened to paste text: the text box has the focus
    await importPasted(user)

    expect(api.changes()).toEqual([{ method: 'POST', path: '/api/imports/text', body: { text: PASTED, use_model: true } }])
    // The review starts at the top: focus on its heading, not in a field further down.
    expect(screen.getByRole('heading', { level: 2, name: 'בדיקת טיוטה' })).toHaveFocus()
    expect(screen.getByLabelText('כותרת')).toHaveValue('עוגת תפוזים')
    expect(screen.getByLabelText('קטגוריה')).toHaveValue('') // unresolved: left for the person to choose
    // The original, exactly as pasted, line breaks included.
    const original = screen.getByText('הטקסט המקורי').closest('details')!
    expect(original).toHaveAttribute('open')
    expect(original.querySelector('.original-text-body')?.textContent).toBe(PASTED)
    // The points to check.
    expect(screen.getByRole('heading', { name: 'לבדיקה (2)' })).toBeInTheDocument()
    expect(screen.getByText(AMBIGUOUS.message)).toBeInTheDocument()
    expect(screen.getByText(/הטיוטה מוכנה/)).toBeInTheDocument()
    // The draft is in the gallery, labeled.
    await user.click(screen.getByRole('button', { name: 'מתכונים' }))
    expect(screen.getByRole('button', { name: /עוגת תפוזים/ })).toHaveTextContent('טיוטה')
  })

  it('saves as a recipe only on the explicit button, after the points are handled', async () => {
    const { user, api } = await openImport()
    await importPasted(user)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)

    await user.click(screen.getByRole('button', { name: `טופל: ${AMBIGUOUS.message}` }))
    expect(screen.getByRole('heading', { name: 'לבדיקה (1)' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'שמירה כמתכון' }))
    expect(confirm).toHaveBeenCalledWith('נשארו 1 נקודות שלא סומנו כטופלו. לשמור כמתכון בכל זאת?')
    expect(api.changes()).toHaveLength(1) // "stay": nothing saved

    await user.click(screen.getByRole('button', { name: /^טופל: / }))
    expect(screen.getByText('אין נקודות פתוחות לבדיקה.')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('קטגוריה'), 'קינוחים')
    await user.click(screen.getByRole('button', { name: 'שמירה כמתכון' }))

    expect(await screen.findByText('המתכון נשמר.')).toBeInTheDocument()
    const save = api.changes()[1]
    expect(save.method).toBe('PUT')
    expect(save.body).toMatchObject({ title: 'עוגת תפוזים', category_id: 1, status: 'saved', issues: [] })
    expect(screen.getByRole('heading', { level: 2, name: 'עוגת תפוזים' })).toBeInTheDocument()
    expect(screen.queryByText(/טיוטה מיובאת/)).not.toBeInTheDocument()
    // The original stays with the recipe, closed, in the cooking view.
    expect(screen.getByText('הטקסט המקורי').closest('details')).not.toHaveAttribute('open')
  })

  it('pressing Enter in a field saves a draft, never a recipe', async () => {
    const { user, api } = await openImport()
    await importPasted(user)
    await user.type(screen.getByLabelText('כותרת'), ' של סבתא{Enter}')

    expect(await screen.findByText(/הטיוטה נשמרה/)).toBeInTheDocument()
    expect(api.changes()[1].body).toMatchObject({ title: 'עוגת תפוזים של סבתא', status: 'draft' })
  })

  it('saving as a draft keeps the open points for later', async () => {
    const { user, api } = await openImport()
    await importPasted(user)
    await user.click(screen.getByRole('button', { name: `טופל: ${AMBIGUOUS.message}` }))
    await user.click(screen.getByRole('button', { name: 'שמירת טיוטה' }))

    expect(await screen.findByText(/הטיוטה נשמרה/)).toBeInTheDocument()
    expect(api.changes()[1].body).toMatchObject({
      status: 'draft',
      issues: [{ kind: 'unclear_text', message: 'לא ברור כמה קמח.', quote: '200 גרם קמח' }],
    })
    expect(screen.getByText(/טיוטה מיובאת שעוד לא נבדקה \(1 נקודות לבדיקה\)/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'בדיקה ושמירה' }))
    expect(screen.getByRole('heading', { name: 'לבדיקה (1)' })).toBeInTheDocument()
  })

  it('keeps the pasted text when Claude fails, and even after a reload', async () => {
    const { user, api, view } = await openImport()
    await user.click(textBox())
    await user.paste(PASTED)
    api.answerNextWith(502, { error: { code: 'extraction_unreachable', message: 'Could not reach the Claude API.', details: null } })
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('אין חיבור ל-Claude API')
    expect(textBox()).toHaveValue(PASTED)
    expect(api.recipes()).toHaveLength(sampleRecipes.length) // nothing saved

    view.unmount() // a reload: the page starts again from nothing, at the address it was at
    render(<App />)
    expect(await screen.findByLabelText('טקסט המתכון')).toHaveValue(PASTED)
  })

  it('without an API key, explains and offers to save the text without Claude', async () => {
    const { user, api } = await openImport({ configured: false })
    expect(screen.getByRole('button', { name: 'קריאה עם Claude' })).toBeDisabled()
    await user.click(textBox())
    await user.paste(PASTED)
    await user.click(screen.getByRole('button', { name: 'שמירה בלי עיבוד' }))

    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[0].body).toEqual({ text: PASTED, use_model: false })
    expect(screen.getByText('הטקסט נשמר בלי עיבוד.')).toBeInTheDocument()
    expect(screen.getByText(/נשמר בלי עיבוד$/)).toBeInTheDocument() // the original's summary line
  })

  it('asks for text before sending anything', async () => {
    const { user, api } = await openImport()
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    expect(screen.getByRole('alert')).toHaveTextContent('הדביקו קודם את טקסט המתכון.')
    expect(api.changes()).toEqual([])
  })

  it('an import that finishes after the user moved on adds the draft without pulling them away', async () => {
    const { user, api } = await openImport()
    await user.click(textBox())
    await user.paste(PASTED)
    const release = api.holdNext()
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    expect(await screen.findByText(/Claude קורא את המתכון/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'ביטול' })) // back to the gallery
    release()

    expect(await screen.findByText('הטיוטה "עוגת תפוזים" מוכנה לבדיקה ברשימה.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'בדיקת טיוטה' })).not.toBeInTheDocument() // still in the gallery
    const gallery = within(screen.getByRole('region', { name: 'המתכונים' }))
    expect(gallery.getAllByRole('listitem')[0]).toHaveTextContent('עוגת תפוזים')
  })
})

describe('importing with a local model (Ollama)', () => {
  it('says the text stays on this computer, and names the model', async () => {
    const { user, api } = await openImport({ extraction: LOCAL })
    expect(screen.getByText(/הטקסט נקרא כאן, במחשב הזה/)).toHaveTextContent('qwen3:8b')
    expect(screen.queryByText(/Anthropic/)).not.toBeInTheDocument()
    await user.click(textBox())
    await user.paste(PASTED)
    await user.click(screen.getByRole('button', { name: 'קריאה עם המודל המקומי' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[0].body).toEqual({ text: PASTED, use_model: true })
  })

  it('when the model runs out of time, says so with the limit, keeps the text and can try again', async () => {
    const { user, api } = await openImport({ extraction: LOCAL })
    await user.click(textBox())
    await user.paste(PASTED)
    api.answerNextWith(504, { error: { code: 'extraction_timeout', message: 'English for the API.', details: { seconds: 300 } } })
    await user.click(screen.getByRole('button', { name: 'קריאה עם המודל המקומי' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'המודל לא סיים לקרוא את המתכון בתוך 5 דקות, ולכן הייבוא נעצר ושום דבר לא נשמר.',
    )
    expect(textBox()).toHaveValue(PASTED)
    await user.click(screen.getByRole('button', { name: 'קריאה עם המודל המקומי' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes().map((change) => change.body)).toEqual([
      { text: PASTED, use_model: true },
      { text: PASTED, use_model: true },
    ])
  })

  it('explains when Ollama is not running, and checks again on request', async () => {
    const { user, api } = await openImport({ extraction: { ...LOCAL, configured: false, problem: 'ollama_unreachable' } })
    expect(screen.getByText(/Ollama לא פועל במחשב הזה/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'קריאה עם המודל המקומי' })).toBeDisabled()

    api.setExtraction(LOCAL) // the person started Ollama
    await user.click(screen.getByRole('button', { name: 'בדיקה שוב' }))
    expect(await screen.findByText(/הטקסט נקרא כאן, במחשב הזה/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'קריאה עם המודל המקומי' })).toBeEnabled()
  })

  it('says which command downloads a missing model', async () => {
    await openImport({ extraction: { ...LOCAL, configured: false, problem: 'ollama_model_missing' } })
    expect(screen.getByText(/עוד לא הורד ל-Ollama/)).toHaveTextContent('ollama pull qwen3:8b')
  })
})

describe('importing an Instagram post', () => {
  const POST = 'https://www.instagram.com/p/Cm1mCdCpSzJ/'

  async function importLink(user: ReturnType<typeof userEvent.setup>) {
    await user.click(linkBox())
    await user.paste(POST)
    await user.click(screen.getByRole('button', { name: 'ייבוא מהקישור' }))
  }

  it('reads the post, then opens the draft beside the caption and the link to the post', async () => {
    const { user, api } = await openImport({ extraction: LOCAL })
    await importLink(user)
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })

    expect(api.changes()).toEqual([{ method: 'POST', path: '/api/imports/link', body: { url: POST, use_model: true } }])
    const original = screen.getByText('הטקסט המקורי').closest('details')!
    expect(original).toHaveTextContent('כיתוב מהפוסט באינסטגרם')
    expect(original.querySelector('.original-text-body')?.textContent).toBe(INSTAGRAM_CAPTION)
    expect(within(original).getByRole('link', { name: POST })).toHaveAttribute('href', POST)
  })

  it('says what it is doing while the post and the recipe are read', async () => {
    const { user, api } = await openImport({ extraction: LOCAL })
    const release = api.holdNext()
    await importLink(user)
    expect(await screen.findByText(/קורא את הכיתוב מהפוסט באינסטגרם, ואז המודל המקומי מסדר אותו/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'קורא…' })).toBeInTheDocument()
    release()
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
  })

  it('when the post cannot be read, says why, keeps the link and offers pasting the caption', async () => {
    const { user, api } = await openImport()
    api.answerNextWith(502, {
      error: { code: 'instagram_unavailable', message: "Instagram says this post isn't available.", details: { url: POST, caption: null } },
    })
    await importLink(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('אינסטגרם אומר שהפוסט לא זמין')
    expect(alert).toHaveTextContent('להדביק אותו בתיבה למטה; הקישור יישמר עם המתכון')
    expect(linkBox()).toHaveValue(POST)
    expect(textBox()).toHaveFocus()
    expect(api.recipes()).toHaveLength(sampleRecipes.length) // nothing saved

    await user.paste(PASTED)
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[1].body).toEqual({ text: PASTED, use_model: true, url: POST })
  })

  it('puts a caption that may be cut off in the box, and flags it if it is sent unchanged', async () => {
    const preview = 'עוגת לימון של סבתא 🍋\n3 ביצים…'
    const { user, api } = await openImport()
    api.answerNextWith(409, {
      error: { code: 'instagram_caption_incomplete', message: 'Only a preview.', details: { url: POST, caption: preview } },
    })
    await importLink(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('ייתכן שהיא קטועה')
    expect(screen.getByRole('alert')).toHaveTextContent('השלימו את החסר')
    expect(textBox()).toHaveValue(preview)
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[1].body).toEqual({ text: preview, use_model: true, url: POST, possibly_incomplete: true })
  })

  it('asks before replacing text already in the box with a caption read from the post', async () => {
    const { user, api } = await openImport()
    await user.click(textBox())
    await user.paste(PASTED)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    api.answerNextWith(422, {
      error: { code: 'not_a_recipe', message: 'No recipe.', details: { url: POST, caption: INSTAGRAM_CAPTION } },
    })
    await importLink(user)

    expect(await screen.findByRole('alert')).toHaveTextContent('לא נמצא מתכון בטקסט.')
    expect(confirm).toHaveBeenCalledWith('להחליף את הטקסט שבתיבה בכיתוב שנקרא מהפוסט?')
    expect(textBox()).toHaveValue(PASTED) // kept: the person said no
  })

  it('explains an address that is not a post, and leaves the focus on the link', async () => {
    const { user, api } = await openImport()
    api.answerNextWith(422, {
      error: { code: 'invalid_instagram_url', message: 'Only links to a single post or Reel are supported.', details: null },
    })
    await importLink(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('זה לא נראה כמו קישור לפוסט')
    expect(linkBox()).toHaveFocus()
  })

  it('asks for a link before sending anything', async () => {
    const { user, api } = await openImport()
    await user.click(screen.getByRole('button', { name: 'ייבוא מהקישור' }))
    expect(screen.getByRole('alert')).toHaveTextContent('הדביקו קודם קישור למתכון.')
    expect(api.changes()).toEqual([])
  })

})

describe('importing a recipe page from a website', () => {
  const PAGE = 'https://www.example-recipes.co.il/recipes/orange-cake/'

  async function importPage(user: ReturnType<typeof userEvent.setup>) {
    await user.click(linkBox())
    await user.paste(PAGE)
    await user.click(screen.getByRole('button', { name: 'ייבוא מהקישור' }))
  }

  it('reads the page through the same field, then opens the draft beside the page\'s recipe data', async () => {
    const { user, api } = await openImport({ extraction: LOCAL })
    expect(screen.getByText(/ודפי מתכונים מאתרים/)).toBeInTheDocument() // what the field accepts
    const release = api.holdNext()
    await importPage(user)
    expect(await screen.findByText(/קורא את דף המתכון, ואז המודל המקומי מסדר אותו/)).toBeInTheDocument()
    release()
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })

    expect(api.changes()).toEqual([{ method: 'POST', path: '/api/imports/link', body: { url: PAGE, use_model: true } }])
    const original = screen.getByText('הטקסט המקורי').closest('details')!
    expect(original).toHaveTextContent('נתוני המתכון שבדף')
    expect(original).toHaveTextContent('הקטגוריה נבחרה על ידי qwen3:8b')
    expect(within(original).getByRole('link', { name: PAGE })).toHaveAttribute('href', PAGE)
    expect(original).toHaveTextContent('המטבח של רותי')
  })

  it('a page that cannot be read says why, keeps the link, and offers pasting the recipe with it', async () => {
    const { user, api } = await openImport()
    api.answerNextWith(502, { error: { code: 'website_blocked', message: 'Refused (HTTP 403).', details: { url: PAGE } } })
    await importPage(user)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('האתר סירב לשלוח את הדף למחברת')
    expect(alert).toHaveTextContent('אפשר להעתיק את המתכון מהדף ולהדביק אותו בתיבה למטה; הקישור יישמר עם המתכון.')
    expect(linkBox()).toHaveValue(PAGE)
    expect(textBox()).toHaveFocus()

    await user.paste(PASTED)
    expect(screen.getByText(/הקישור שלמעלה יישמר עם המתכון כמקור/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[1].body).toEqual({ text: PASTED, use_model: true, url: PAGE })
  })

  it.each([
    ['website_no_recipe', 'הדף נקרא, אבל לא נמצא בו מתכון.'],
    ['website_incomplete', 'לא הצלחנו לחלץ מהעמוד מתכון מלא'],
    ['website_ambiguous', 'בדף יש כמה מתכונים, ולא ברור איזה מהם הוא המתכון של הדף.'],
    ['website_not_found', 'האתר אומר שאין דף כזה.'],
    ['website_timeout', 'האתר לא ענה בזמן.'],
  ])('explains %s in Hebrew and offers pasting the text', async (code, message) => {
    const { user, api } = await openImport()
    api.answerNextWith(422, { error: { code, message: 'English for the API.', details: { url: PAGE } } })
    await importPage(user)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(alert).toHaveTextContent('אפשר להעתיק את המתכון מהדף')
  })

  it('an address on this computer or a private network is refused, with the focus on the link', async () => {
    const { user, api } = await openImport()
    api.answerNextWith(422, { error: { code: 'website_forbidden_address', message: 'Private.', details: { url: PAGE } } })
    await importPage(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('הכתובת מובילה למחשב הזה או לרשת פרטית')
    expect(linkBox()).toHaveFocus()
  })

  it('the same page again shows the recipe that has it', async () => {
    const { user, api } = await openImport()
    const [cake] = sampleRecipes
    api.answerNextWith(409, {
      error: { code: 'duplicate_link', message: 'Here already.', details: { url: PAGE, matches: [{ id: cake.id, title: cake.title, status: 'saved' }] } },
    })
    await importPage(user)
    expect(await screen.findByText('הדף הזה כבר במחברת')).toBeInTheDocument()
  })
})

describe('the import strip above the gallery', () => {
  const POST = 'https://www.instagram.com/p/Cm1mCdCpSzJ/'

  async function renderGallery() {
    const user = userEvent.setup()
    const api = fakeApi({ recipes: sampleRecipes, categories: sampleCategories, extraction: CLAUDE })
    render(<App />)
    const strip = within(await screen.findByRole('region', { name: 'ייבוא מתכון מקישור' }))
    return { user, api, strip }
  }

  it('reads an Instagram link at once and opens the draft for review', async () => {
    const { user, api, strip } = await renderGallery()
    await user.click(strip.getByLabelText('קישור למתכון'))
    await user.paste(POST)
    await user.click(strip.getByRole('button', { name: 'ייבוא' }))

    expect(await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })).toBeInTheDocument()
    expect(api.changes()).toEqual([{ method: 'POST', path: '/api/imports/link', body: { url: POST, use_model: true } }])
  })

  it('reads a recipe page at once, the same way', async () => {
    const { user, api, strip } = await renderGallery()
    await user.type(strip.getByLabelText('קישור למתכון'), 'www.example-recipes.co.il/cake')
    await user.click(strip.getByRole('button', { name: 'ייבוא' }))
    expect(await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })).toBeInTheDocument()
    expect(api.changes()).toEqual([{ method: 'POST', path: '/api/imports/link', body: { url: 'www.example-recipes.co.il/cake', use_model: true } }])
  })

  it('"ייבוא מתכון" in the top bar moves to the link field', async () => {
    const { user, strip } = await renderGallery()
    await user.click(screen.getByRole('button', { name: 'ייבוא מתכון' }))
    expect(strip.getByLabelText('קישור למתכון')).toHaveFocus()
  })

  it('asks for a link, and says when what was typed is not one, sending nothing', async () => {
    const { user, api, strip } = await renderGallery()
    await user.click(strip.getByRole('button', { name: 'ייבוא' }))
    expect(strip.getByText('הדביקו קודם קישור למתכון.')).toBeInTheDocument()
    await user.type(strip.getByLabelText('קישור למתכון'), 'עוגת שוקולד')
    await user.click(strip.getByRole('button', { name: 'ייבוא' }))
    expect(strip.getByText('זה לא נראה כמו קישור. קישור מתחיל ב-https://')).toBeInTheDocument()
    expect(api.changes()).toEqual([])
  })
})

describe('the import strip on a phone', () => {
  it('stays closed until "ייבוא מתכון" opens it, then the link field has the focus', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: query === '(max-width: 700px)',
      addEventListener: () => {},
      removeEventListener: () => {},
    }))
    const user = userEvent.setup()
    fakeApi({ recipes: sampleRecipes, categories: sampleCategories, extraction: CLAUDE })
    render(<App />)
    await screen.findByRole('region', { name: 'המתכונים' })
    const button = screen.getByRole('button', { name: 'ייבוא מתכון' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('region', { name: 'ייבוא מתכון מקישור' })).not.toBeInTheDocument()

    await user.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(within(screen.getByRole('region', { name: 'ייבוא מתכון מקישור' })).getByLabelText('קישור למתכון')).toHaveFocus()
    await user.click(button)
    expect(screen.queryByRole('region', { name: 'ייבוא מתכון מקישור' })).not.toBeInTheDocument()
  })
})

describe('a post that is already in the notebook', () => {
  const POST = 'https://www.instagram.com/reel/Cm1mCdCpSzJ/?igsh=abc'
  const [cake] = sampleRecipes
  const duplicate = {
    error: {
      code: 'duplicate_link',
      message: 'This post is already in the notebook.',
      details: { url: 'https://www.instagram.com/reel/Cm1mCdCpSzJ/', matches: [{ id: cake.id, title: cake.title, status: 'saved' }] },
    },
  }

  async function importExisting() {
    const result = await openImport()
    result.api.answerNextWith(409, duplicate)
    await result.user.click(linkBox())
    await result.user.paste(POST)
    await result.user.click(screen.getByRole('button', { name: 'ייבוא מהקישור' }))
    await screen.findByText('הפוסט הזה כבר במחברת')
    return result
  }

  it('shows the recipe that has it, and opens it on request', async () => {
    const { user, api } = await importExisting()
    const notice = screen.getByRole('alert')
    expect(notice).toHaveTextContent(cake.title)
    expect(notice).toHaveTextContent('מתכון')
    await user.click(within(notice).getByRole('button', { name: `פתיחת ${cake.title}` }))
    expect(screen.getByRole('heading', { level: 2, name: cake.title })).toBeInTheDocument()
    expect(api.changes()).toHaveLength(1) // only the import that stopped: nothing saved, nothing replaced
  })

  it('imports another copy only when asked', async () => {
    const { user, api } = await importExisting()
    await user.click(screen.getByRole('button', { name: 'ייבוא עותק נוסף' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes().map((call) => call.body)).toEqual([
      { url: POST, use_model: true },
      { url: POST, use_model: true, allow_duplicate: true },
    ])
  })

  it('checks a link that comes with pasted text too, and keeps the choice for it', async () => {
    const { user, api } = await openImport()
    await user.click(linkBox())
    await user.paste(POST)
    await user.click(textBox())
    await user.paste(PASTED)
    api.answerNextWith(409, duplicate)
    await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('הפוסט הזה כבר במחברת')
    await user.click(screen.getByRole('button', { name: 'ייבוא עותק נוסף' }))
    await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
    expect(api.changes()[1].body).toEqual({ text: PASTED, use_model: true, url: POST, allow_duplicate: true })
  })
})
