/// <reference types="vitest/config" />
import { cpSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// The public, read-only copy (`npm run build:public`, docs/public-notebook.md) is built from the recipes
// exported by backend/scripts/export_public.py. Both live in the git-ignored data folder:
// data/public-notebook/export (the recipes and their pictures) and data/public-notebook/site (the page).
const PUBLIC_FOLDER = resolve(import.meta.dirname, process.env.PUBLIC_NOTEBOOK_FOLDER ?? '../data/public-notebook')
const PUBLIC_EXPORT = join(PUBLIC_FOLDER, 'export')
const PUBLIC_SITE = join(PUBLIC_FOLDER, 'site')

/** Puts the exported recipes and pictures beside the built page, and refuses to build without them. */
function publicNotebookFiles(): Plugin {
  return {
    name: 'public-notebook-files',
    apply: 'build',
    buildStart() {
      if (!existsSync(join(PUBLIC_EXPORT, 'notebook.json'))) {
        this.error(`No exported recipes in ${PUBLIC_EXPORT}. Run "uv run python -m scripts.export_public" in backend/ first.`)
      }
    },
    // Into the folder this build writes: the site/ folder, or the one the publish command checks first (--outDir).
    writeBundle(options) {
      cpSync(PUBLIC_EXPORT, options.dir ?? PUBLIC_SITE, { recursive: true })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react(), ...(mode === 'public' ? [publicNotebookFiles()] : [])],
  // Relative addresses: the public copy works from any folder on any static host.
  base: mode === 'public' ? './' : '/',
  build: mode === 'public' ? { outDir: PUBLIC_SITE, emptyOutDir: true } : {},
  // `npm run preview:public` serves only the files, like the static host: no /api forwarding to the backend.
  preview: mode === 'public' ? { proxy: {} } : {},
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
}))
