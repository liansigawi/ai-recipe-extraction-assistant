/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Requests to /api/... are forwarded to FastAPI. The browser only ever talks to
    // this dev server, so the backend needs no CORS rules and stays on 127.0.0.1.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom', // a simulated browser document, so components can render in Node
    setupFiles: ['./src/test/setup.ts'],
  },
})
