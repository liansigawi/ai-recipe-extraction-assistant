// The entry point: Vite loads this file from index.html.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// The page's font, bundled with it (OFL-1.1): Hebrew and Latin letters, every weight in one file each.
import '@fontsource-variable/rubik'
import App from './App.tsx'
import './index.css'

// createRoot attaches React to the <div id="root"> in index.html; render draws the App into it.
// StrictMode runs extra development-only checks that surface common mistakes early: for example,
// it runs each effect twice, which shows whether the effect's cleanup is right.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
