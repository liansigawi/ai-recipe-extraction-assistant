import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { AMBIGUOUS, fakeApi, type DraftMaker } from './test/fakeApi'
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
  await user.click(await screen.findByRole('button', { name: 'ייבוא מטקסט' }))
  // Wait until the panel knows whether and how the model can be used.
  await screen.findByText(
    !extraction.configured ? /אפשר לשמור את הטקסט בלי עיבוד/ : extraction.local ? /ולא נשלח לשום מקום/ : /נשלחים ל-Anthropic/,
  )
  return { user, api, view }
}

const textBox = () => screen.getByLabelText('טקסט המתכון')

async function importPasted(user: ReturnType<typeof userEvent.setup>) {
  await user.click(textBox())
  await user.paste(PASTED)
  await user.click(screen.getByRole('button', { name: 'קריאה עם Claude' }))
  await screen.findByRole('heading', { level: 2, name: 'בדיקת טיוטה' })
}

describe('importing pasted text', () => {
  it('sends the text, then opens the draft for review beside the original', async () => {
    const { user, api } = await openImport()
    expect(textBox()).toHaveFocus()
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
    // The draft is in the list, labeled.
    const card = screen.getByRole('button', { name: /עוגת תפוזים/ })
    expect(card).toHaveTextContent('טיוטה')
    expect(screen.getByText(/הטיוטה מוכנה/)).toBeInTheDocument()
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
    expect(screen.getByRole('button', { name: /עוגת תפוזים/ })).not.toHaveTextContent('טיוטה')
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

    view.unmount() // a reload: the page starts again from nothing
    render(<App />)
    await user.click(await screen.findByRole('button', { name: 'ייבוא מטקסט' }))
    expect(textBox()).toHaveValue(PASTED)
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

    await user.click(screen.getByRole('button', { name: 'ביטול' })) // back to the recipe list
    release()

    expect(await screen.findByText('הטיוטה "עוגת תפוזים" מוכנה לבדיקה ברשימה.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'עוגת שוקולד עם גנאש' })).toBeInTheDocument() // still here
    const list = within(within(screen.getByRole('navigation')).getByRole('list'))
    expect(list.getAllByRole('button')[0]).toHaveTextContent('עוגת תפוזים')
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
