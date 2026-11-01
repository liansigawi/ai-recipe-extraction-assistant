# The public, read-only notebook

A copy of chosen recipes at a public address that anyone can open in a browser: no installation, no
account, no API key, no GPU, and this computer can be off. It is the same React interface built as
static files and hosted on Cloudflare Pages. Visitors browse, search and filter the recipes, open them,
see the cooked marks as saved, read a short page about the project, and, for a few recipes, see the
original text beside the saved recipe. Nothing in it can change data: there is no server behind it.

Your notebook itself is unchanged: importing, editing and everything else work as before. The public
copy changes only when you run the update command, never on its own.

## Update the public notebook: one command

From the project root, in PowerShell or cmd:

```powershell
.\publish-notebook.cmd
```

It exports the recipes chosen in `data/public-notebook/selection.json` (the notebook is opened
read-only), builds the site, checks it, uploads it to the same address, and checks that the address shows
the new version. It ends with `Published: https://...`, or with `FAILED.` and the reason. Each step starts
only after the one before it succeeded, so a failed export, build, check or upload leaves the published
notebook as it was (the message says so). Your edits to a chosen recipe appear at the next successful run.

| Command | What it does |
|---|---|
| `.\publish-notebook.cmd` | export, build, check, publish, check the address |
| `.\publish-notebook.cmd --add 18` | adds saved recipe 18 to the selection, then publishes (several: `--add 18 19 20`) |
| `.\publish-notebook.cmd --remove 12` | takes recipe 12 out of the selection, then publishes |
| `.\publish-notebook.cmd --list` | every recipe: can it be published, is it in the selection |
| `.\publish-notebook.cmd --no-deploy` | export, build and check only; then `npm run preview:public` in `frontend/` shows it at http://localhost:4173 |

(From `backend/`, the same is `uv run python -X utf8 -m scripts.publish_public ...`.)

## Add a recipe you saved to the public notebook

1. Save it in the notebook as usual (a draft cannot be published: open it, check it, "שמירה כמתכון").
2. Find its number: the end of its address in the notebook (`http://localhost:5173/#/recipes/18` is 18), or
   `.\publish-notebook.cmd --list`.
3. Run `.\publish-notebook.cmd --add 18` (several at once: `--add 18 19 20`). It refuses a draft, a sample or
   a number the notebook does not have, and then changes nothing.

To give it a "מהמקור למתכון" page as well, add its number to `show_processing` in
`data/public-notebook/selection.json` (it must have been imported, not typed in), then run the command.

## One-time setup (before the first publication)

1. Create a free Cloudflare account at https://dash.cloudflare.com/sign-up. The free plan is enough; nothing
   here needs a paid plan or a paid add-on.
2. In `frontend/`, run `npx wrangler login`. It opens the browser; allow access for Wrangler. Wrangler keeps
   this login in your Windows user profile, never in this project, in Git or in the published files.
   `npx wrangler logout` removes it.
3. Run `.\publish-notebook.cmd`. The first run creates the Cloudflare Pages project `recipe-notebook`
   (another name: add `--project <name>` to that first run). Its address is `https://recipe-notebook.pages.dev`,
   or the same with a short suffix if someone already has that name; the command prints it and keeps it in
   `data/public-notebook/site.json`. Every later run publishes to the same project and address.

## Choosing the recipes: `data/public-notebook/selection.json`

```json
{
  "recipes": [17, 15, 13, 12, 11, 10],
  "show_processing": [17, 15, 12],
  "repository_url": null
}
```

- `recipes`: the recipe numbers to publish. Only saved recipes: a draft, an invented sample or a number the
  notebook no longer has stops the run before anything is built or uploaded.
- `show_processing`: of those, the recipes that get a "מהמקור למתכון" page.
- `repository_url`: the project's code, linked from the "about" page; `null` shows no link.

## What becomes public, and what never does

Each run lists what becomes public, recipe by recipe: its credit, whether its original text is public, and
its cover.

Public, per recipe: title, category and subcategory names, servings, ingredient and step groups, notes,
sources with their credit and links, the cooked mark, the creation and last-saved times, and the cover
picture (for a video, a still from it, with the link to the post; never the video). For the recipes in
`show_processing`, also: the imported original text as it was read (a caption's hashtags, mentions and
promotions included), where it came from, which model read it and when, and the import's own draft if a
database backup kept it (below).

Never public: the database, the descriptions written for the model's category choice, review points,
drafts and samples, the other recipes' original texts, any picture besides the cover, videos, uploaded
pictures (a phone photo can carry the place it was taken; a recipe whose cover is an upload shows its
category's drawing), `.env`, API keys, the Cloudflare login, evaluation data, screenshots and the rest of
`data/`. Before uploading, the command checks the built site: only the expected files, every picture the
recipes name and no other, and no API key of this computer or name of its folders in any file.

## The comparison page: only records that exist

The "מהמקור למתכון" page shows the original text exactly as read (`recipe_imports.original_text`, which
editing never changes), the saved recipe with the quantity read from each ingredient line highlighted, and
the import's draft with what review changed, only when a copy of that draft exists. Saving a recipe
replaces its draft in the database, so a draft survives only in a backup that `app/migrate.py` made while
the recipe was still an untouched draft. The export looks through `data/recipes.backup-*.db` for one: the
same recipe (same number and creation time), still a draft, never saved since the import. Without one, the
page says that no draft was kept. Nothing is reconstructed or re-run.

## Costs and limitations

- **Cost: none** on Cloudflare's free plan. Cloudflare's documentation: "On both free and paid plans,
  requests to static assets are free and unlimited." Its other limits (500 builds a month, 20,000 files of
  up to 25 MiB each per site) are far above what this needs: one run uploads about 20 files.
- **Every deployment keeps its own address.** Cloudflare gives each upload a permanent address of its own
  (`https://<id>.recipe-notebook.pages.dev`) besides the main one. A recipe you take out of the selection
  disappears from the main address, but stays at the older deployments' addresses until you delete those
  deployments (Cloudflare dashboard, Workers & Pages, the project, Deployments).
- **Not automatic.** A save in the notebook is not published until you run the command.
- **A Cloudflare address.** `*.pages.dev`; your own domain is possible later (Cloudflare dashboard).
- **Hebrew interface.** The pages are in Hebrew, like the notebook; the technical README is in English.

## Check the published site

```powershell
cd backend
uv run python -m scripts.check_public_site https://recipe-notebook.pages.dev
```

It uses the public address only, in a real browser: the gallery and every picture, search and each filter,
every recipe and comparison page by its direct link and after a reload, the back button, the about page,
the phone width, no control that changes data, a change sent to the site changing nothing, no API behind
it, nothing loaded from other sites. One line per check; exit code 0 only when all passed.

## How it works

- `publish-notebook.cmd` runs `backend/scripts/publish_public.py`, which calls the export, then
  `npm run build:public` into `data/public-notebook/site.partial/`, checks that folder, swaps it in as
  `site/`, uploads it with Wrangler (`wrangler pages deploy ... --branch main`; Wrangler is `frontend/`'s
  dev dependency, pinned) and fetches `notebook.json`, the page and every picture from the address.
  Cloudflare moves the address to a new deployment only after the whole upload succeeded.
- `backend/scripts/export_public.py` reads the notebook through the backend's own code (`crud`, the shape
  the API returns), keeps only the fields above, copies the cover pictures, and writes
  `data/public-notebook/export/` in full before replacing the previous export. On its own:
  `uv run python -m scripts.export_public [--list]` in `backend/`.
- `frontend/vite.config.ts`, mode `public`: relative addresses (any host, any folder), the export copied
  beside the page, no `/api` forwarding in `npm run preview:public`; the build stops if there is no export.
  Another folder: `PUBLIC_NOTEBOOK_FOLDER` for the build, `--folder` for the scripts.
- `frontend/src/publicNotebook.ts` says whether the page is the public copy. `App.tsx` then reads
  `notebook.json` instead of the API (`loadPublicNotebook` in `api.ts`), leaves out importing, editing,
  deleting, the cooked controls, media changes and the categories screen, and sends any address of those
  pages to the gallery. `SourceComparison.tsx` is the comparison page (its differences come from
  `processing.ts`), `AboutPage.tsx` the page about the project.
- Tests: `backend/tests/test_export_public.py`, `backend/tests/test_publish_public.py` (npm, Wrangler and
  the address are stand-ins: nothing is built or uploaded), `frontend/src/App.public.test.tsx`,
  `frontend/src/processing.test.ts`.
