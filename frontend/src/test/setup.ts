// Runs before every test file.
import '@testing-library/jest-dom/vitest' // adds matchers such as expect(element).toBeInTheDocument()
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup() // remove what each test rendered, so tests cannot affect each other
  vi.unstubAllGlobals() // put back anything a test replaced, such as fetch (test/fakeApi.ts)
  vi.restoreAllMocks()
  localStorage.clear() // e.g. the import screen's kept text
  window.history.replaceState(null, '', '/') // the page's place (route.ts) starts at the gallery again
})

// jsdom lays nothing out, so it cannot scroll: App's scrolling is a no-op here.
window.scrollTo = () => {}

// jsdom has <dialog> but not its showModal() and close(): enough of them for the media viewer.
if (typeof HTMLDialogElement !== 'undefined' && typeof HTMLDialogElement.prototype.showModal !== 'function') {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
}
