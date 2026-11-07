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
- `demonstrations` (optional): recipe number -> a recorded demonstration (a JSON file, its path from this
  folder), shown on that recipe's "מהמקור למתכון" page (below). Only for recipes in `show_processing`.
- `classification_checks` (optional): recipe number -> a recorded classification check (a JSON file, its path
  from this folder), for a recipe in `show_processing` whose import draft was not kept and that has no
  demonstration (below).

## What becomes public, and what never does

Each run lists what becomes public, recipe by recipe: its credit, whether its original text is public, and
its cover.

Public, per recipe: title, category and subcategory names (a dessert's type), a dessert's healthy style,
servings, ingredient and step groups (a line the app derived from a step, with its label and the step's
sentence), notes,
sources with their credit and links, the cooked mark, the creation and last-saved times, and the cover
picture (for a video, a still from it, with the link to the post; never the video). For the recipes in
`show_processing`, also: the imported original text as it was read (a caption's hashtags, mentions and
promotions included), where it came from, which model read it and when, and the import's own draft if a
database backup kept it (below).

Never public: the database, the descriptions written for the model's category choice, review points and
the review decisions of the notebook's recipes (a demonstration's own are part of it),
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
page says, in one sentence, that the original import's draft was not kept. Nothing is reconstructed or
re-run for it.

Every comparison page has a "סיווג" block: "הצעת המודל לפני הבדיקה" beside "הסיווג לאחר הבדיקה", each as
a main category and, for a dessert, its type (the healthy style is not part of it: the model does not set
it), and each with the record it comes from:
- a demonstration: its draft's category, and the category after the review performed while preparing it;
- a kept import draft: its category, and the saved recipe's;
- a classification check, for a recipe with neither: the recipe's original imported again on a separate copy
  of the notebook, and that draft's classification request answered, then sent again unchanged. The file
  (`data/public-notebook/classifications/<id>.json`, git-ignored) records the run's time and model, a
  fingerprint of the text it imported, and each answer as the import mapped it. The page says it is a fresh
  run, not the original import's suggestion, and whether the answers agreed. After review is the saved
  recipe's category. The export refuses a check not made from the recipe's own original text, and a check
  for a recipe whose import draft is kept or that has a demonstration;
- none of these: the block says the original import's suggestion was not kept.

A recipe with a **demonstration** shows that instead, as what it is: the recipe's original text imported
again with the current system, on a separate copy of the notebook, and reviewed there. Its file
(`data/public-notebook/demonstrations/`, git-ignored; a newer run gets a file of its own, in a folder named
by its date, and the selection names the one shown) records:
- the draft exactly as that import saved it, its review points included;
- the same recipe after its review, as it was saved, with each point's decision (added, dismissed or
  handled);
- the run's time, model, code revision and settings, and a fingerprint of the text it imported;
- under `answer`, what the model itself answered: its classification as given, and each review point it
  raised, with the rule that left it out when the import did not show it (an "unclear or" in a passage with
  no "או", a passage the model itself left out, a point with no passage, another check);
- under `automatic`, what the import did by fixed rules rather than the model: a bracket remark joined to
  its step, a line that refers to a separate recipe kept as written.

The export refuses a demonstration not made from that recipe's own original text, and evidence that does
not hold: a joined remark that the rule, the original and both recorded states do not all show; a kept
reference that is not the original's words, not a reference by the rule, or not where the draft has it; a
model classification other than the draft's category; a model point whose words are not in the original,
one left out for having no "או" whose passage has one, or one shown that the draft does not have.

The page then has:
- a one-line introduction ("הדגמה של ייבוא מחדש באמצעות הגרסה המעודכנת של המערכת."), with the date, the
  model, its temperature and the code revision, and a short note on the original import's draft (not kept,
  or kept apart and not shown) and that the saved recipe was not replaced;
- "מה נעשה, ומי עשה", in three parts: the model (what its labels copied word for word, its title, its
  category, how many points it raised and how many were shown); the system by fixed rules (the quantity read
  from each line, a remark joined, a reference kept, the model's points it left out and why, the points it
  raised by its own checks); and the review performed while preparing the demonstration, listing only what
  it changed, part by part, as lines removed and added, and naming the parts it left as they were. What a
  rule did, or a wrong category the model chose, is never shown as a review change;
- "סיווג", the classification before and after review (above);
- the review points, each with who raised it (the model or the system), the passage it quotes and what
  review decided, or "הייבוא לא סימן נקודות לבדיקה.";
- the original text beside "המתכון לאחר הבדיקה", the demonstration's reviewed result, where a line added
  from a point says "נוסף בעקבות התרעה" and opens its sentence;
- folded under "הצגת הטיוטה לפני הבדיקה": the draft as the import saved it, with the model's category.

Decisions are text, never buttons: the public copy changes nothing. The other recipes keep the saved
recipe's comparison.

The five comparison pages show demonstrations run on 2026-11-07, 11:51-11:53 UTC, with qwen3:8b
(temperature 0, labeling mode, 8,192 tokens) at code 75bfd06: the first completed run of each, none retried,
each on its own copy of the notebook. Each read its recipe's preserved original through the text import,
which hands it to the same function as the Instagram or website import did, without fetching the post or
the page again (so without its pictures). Inputs, raw answers, drafts, copies and the review script are in
`data/evals/extraction/20261107-five-demonstrations/`. The reviews were performed while preparing them:
- 12: the model chose "קינוחים · טארטים ופאי"; the system raised one point (strawberries only in the
  steps) and joined the oven remark to its step. Review added the strawberries, with no amount, and
  corrected the type to "עוגות".
- 15: the model chose "קינוחים · עוגות"; no point. Review put the remark in brackets about a tall cake's
  baking time back into its baking step (the original writes it on that step's line; the draft made it a
  note).
- 17: the model chose "קינוחים · גלידות וקינוחים קפואים"; no point. Review corrected the category to
  "משקאות".
- 14: the model chose "קינוחים · מאפים מתוקים"; the system raised one point (a remark on the cheese kept as
  a note), marked done. Review corrected the category to "ארוחות קלילות" and restored the yield line the
  model left out, "מהתערובת הכנתי 4 פנקייקים, הערכים ליחידה-", before the nutrition values it introduces.
  The saved recipe lacks that line too; it was not changed.
- 29: the model chose "קינוחים · מאפים מתוקים", right; the system kept both lines that refer to the
  separate dough recipe, left out the model's five "unclear or" points (no "או" in those passages) and
  raised two points (the title chosen from the opening line, the separate recipe), both marked done. Review
  changed nothing.

The demonstrations of 2026-11-05 (12, 17 and 29) are kept beside them in `demonstrations/`, unpublished,
and recipe 15's classification check in `classifications/15.json`.

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
