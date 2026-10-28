import { describe, expect, it } from 'vitest'
import { linkKind } from './importLinks'

describe('which importer a link goes to', () => {
  it('Instagram posts and reels, with or without www', () => {
    expect(linkKind('https://www.instagram.com/p/CLJ5G9rDi1a/')).toBe('instagram')
    expect(linkKind('  https://instagram.com/reel/Cm1mCdCpSzJ/?igsh=x ')).toBe('instagram')
    expect(linkKind('http://m.instagram.com/p/x')).toBe('instagram')
  })

  it('any other web address is a website (not supported yet)', () => {
    expect(linkKind('https://www.example-recipes.co.il/cake')).toBe('website')
    expect(linkKind('https://notinstagram.com/p/x')).toBe('website')
  })

  it('nothing, or something that is not a web link', () => {
    expect(linkKind('   ')).toBe('empty')
    expect(linkKind('instagram.com/p/x')).toBe('not_a_link')
    expect(linkKind('javascript:alert(1)')).toBe('not_a_link')
  })
})
