// Runs before every test file.
import '@testing-library/jest-dom/vitest' // adds matchers such as expect(element).toBeInTheDocument()
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup() // remove what each test rendered, so tests cannot affect each other
  vi.unstubAllGlobals() // put back anything a test replaced, such as fetch (test/fakeApi.ts)
  vi.restoreAllMocks()
  localStorage.clear() // e.g. the import screen's kept text
})
