// The entry point: Vite loads this file from index.html.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import { sampleRecipes } from './sampleRecipes.ts'

// createRoot attaches React to the <div id="root"> in index.html; render draws the App into it.
// StrictMode runs extra development-only checks that surface common mistakes early.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App recipes={sampleRecipes} />
  </StrictMode>,
)
