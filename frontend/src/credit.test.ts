import { describe, expect, it } from 'vitest'
import { creatorsFromText, creatorToText, creditedSource, postLink, shownName } from './credit'
import type { Source } from './types'

describe('the credit', () => {
  it('reads the editor text: a name, an @username, or both, separated by commas', () => {
    expect(creatorsFromText('ריטה קדוש @ritakadosh_, @alehonline, Example Kitchen, ')).toEqual([
      { name: 'ריטה קדוש', username: 'ritakadosh_' },
      { name: null, username: 'alehonline' },
      { name: 'Example Kitchen', username: null },
    ])
    expect(creatorsFromText('Lior Mashiach | ליאור משיח (@lioroooosh)')).toEqual([
      { name: 'Lior Mashiach | ליאור משיח', username: 'lioroooosh' },
    ])
    expect(creatorsFromText('@not-a-handle')).toEqual([{ name: '@not-a-handle', username: null }]) // not a valid username
  })

  it('writes it back the same way', () => {
    const credits = [{ name: 'ריטה קדוש', username: 'ritakadosh_' }, { name: null, username: 'alehonline' }]
    expect(credits.map(creatorToText).join(', ')).toBe('ריטה קדוש @ritakadosh_, @alehonline')
    expect(creatorsFromText(credits.map(creatorToText).join(', '))).toEqual(credits)
  })

  it('does not repeat a name that only repeats the username', () => {
    expect(shownName({ name: 'alehonline', username: 'alehonline' })).toBeNull()
    expect(shownName({ name: 'ריטה קדוש', username: 'ritakadosh_' })).toBe('ריטה קדוש')
  })

  it('credits the first source with creators, and links the original post', () => {
    const sources: Source[] = [
      { kind: 'text', url: null, creators: [] },
      { kind: 'instagram', url: 'https://www.instagram.com/p/X/', creators: [{ name: null, username: 'baker' }] },
    ]
    expect(creditedSource(sources)).toBe(sources[1])
    expect(postLink(sources)?.url).toBe('https://www.instagram.com/p/X/')
    expect(postLink([{ kind: 'instagram', url: 'https://www.instagram.com/p/Y/', creators: [] }])?.url).toBe('https://www.instagram.com/p/Y/')
  })
})
