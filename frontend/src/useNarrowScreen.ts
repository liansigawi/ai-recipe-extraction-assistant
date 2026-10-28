import { useEffect, useState } from 'react'

const QUERY = '(max-width: 700px)'

function matches(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(QUERY).matches
}

/** True on a phone-sized screen (as in index.css), kept up to date when the window is resized. */
export function useNarrowScreen(): boolean {
  const [narrow, setNarrow] = useState(matches)
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(QUERY)
    const update = () => setNarrow(list.matches)
    list.addEventListener('change', update)
    return () => list.removeEventListener('change', update)
  }, [])
  return narrow
}
