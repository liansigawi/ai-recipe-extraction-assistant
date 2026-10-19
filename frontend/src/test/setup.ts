// Runs before every test file.
import '@testing-library/jest-dom/vitest' // adds matchers such as expect(element).toBeInTheDocument()
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// Remove what each test rendered, so tests cannot affect each other.
afterEach(() => cleanup())
