// The public, read-only copy of the notebook (docs/public-notebook.md): the same pages, built with
// `npm run build:public`. Its recipes come from a file exported beside the page, not from the API, and
// nothing in it changes data. Read when called (not once at load), so a test can switch it on.
export function isPublicNotebook(): boolean {
  return import.meta.env.MODE === 'public'
}
