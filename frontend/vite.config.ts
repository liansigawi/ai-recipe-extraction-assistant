/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Always this port: the backend accepts changes only from pages on localhost:5173
    // (ALLOWED_ORIGINS in backend/app/main.py). If the port is taken, Vite stops instead of
    // quietly moving to another port whose saves the backend would refuse.
    port: 5173,
    strictPort: true,
    // Requests to /api/... are forwarded to FastAPI. The browser only ever talks to
    // this dev server, so the backend needs no CORS rules and stays on 127.0.0.1.
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'jsdom', // a simulated browser document, so components can render in Node
    setupFiles: ['./src/test/setup.ts'],
  },
})
