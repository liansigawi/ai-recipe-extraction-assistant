# Architecture and plan

The plan for the Local Recipe Notebook. The requirements are in [brief.md](brief.md). Items marked
*planned* are decided directionally and get finalized, with tests, in the milestone that builds them.

## Overview

```text
Browser: React + TypeScript (Vite dev server, http://localhost:5173)
   │  fetch("/api/...") JSON          (in development Vite forwards /api to the backend)
   ▼
FastAPI backend (uvicorn, bound to 127.0.0.1:8000)
   ├─ api/             REST routes: recipes (create, read, save, delete) and categories (read),
   │                   milestone 3; imports (planned, milestones 4-5)
   ├─ crud.py          Reads and writes recipes; checks chosen category ids against the database.
   ├─ models + db      SQLAlchemy ORM over SQLite (data/recipes.db), milestone 3.
   ├─ importers/       FETCH source content only: instagram (milestone 1); website,
   │                   screenshots, text (planned, milestones 4-5). No AI.
   ├─ extraction/      (planned, milestone 4) Claude API: source → recipe draft, validated with Pydantic.
   ├─ classification   (planned, milestone 4) The model picks among existing category IDs; the
   │                   backend checks them with crud.check_classification. Never creates categories.
   └─ files            (planned, milestone 5) Uploaded screenshots under data/uploads/, paths in the database.
          │
          └─► Anthropic API (external, from milestone 4): only text/images sent for extraction and classification.
```

**Responsibilities.** React owns the interface and the user's in-progress input. FastAPI owns
everything that needs trust or secrets: fetching sources, calling the model, validating, classifying,
and saving. The Anthropic API key will live only in the backend's environment.

**Local means local.** Both servers listen on this computer only. Data stays in `data/` (or
`RECIPES_DATA_DIR`). The exception, from milestone 4: content you submit for AI extraction is sent to
Anthropic. The README says so now, and the import screen will say so too.

**One origin, and a host check.** In development the browser only talks to the Vite server, which
forwards `/api/...` to FastAPI (`frontend/vite.config.ts`). The page and the API therefore share one
origin, so the backend sends no CORS headers and other sites cannot read its responses. The backend
also answers only requests addressed to `127.0.0.1` or `localhost` (`TrustedHostMiddleware`). That
blocks DNS rebinding, where a malicious page makes the browser reach this computer under its own
host name; such requests get a plain `400 Invalid host header`. Requests that change data (POST,
PUT, DELETE) must also come from the notebook page: a middleware in `main.py` refuses any other
`Origin` with `403 forbidden_origin`, so another site open in the same browser cannot submit
changes. The allowed origins are `localhost:5173` (Vite, with `strictPort`) and `localhost:8000`
(`/docs`). Browsers always send `Origin` with these methods; a request without one comes from a
program on this computer (curl, a script), not from a web page, and is let through.

## How a save travels (milestone 3)

```text
RecipeEditor (form state) ──formToInput──► api.ts: fetch PUT /api/recipes/3, JSON body
   │  the browser adds Origin: http://localhost:5173
   ▼
Vite dev server ──proxy /api──► FastAPI on 127.0.0.1:8000
   1. TrustedHostMiddleware: Host must be localhost or 127.0.0.1           (else 400)
   2. reject_changes_from_other_sites: Origin must be the notebook page    (else 403)
   3. route in api/recipes.py: Pydantic parses the body into RecipeInput   (else 422 invalid_request)
   4. crud.update_recipe: category ids must exist and fit together         (else 422 unknown_category …)
   5. SQLAlchemy: UPDATE recipes …; DELETE/INSERT recipe_sources …; COMMIT (one transaction)
   6. the stored recipe is read back and returned as Recipe JSON (200)
   ▼
App.handleSaved: replaces the recipe in its state → React re-renders the list and the view
```

The page never assumes a save worked: it shows what the server returned. If anything fails, the
editor stays open with the person's text, and the message is shown next to the field the server
named (its `loc` path, mapped back to the form row) or at the bottom of the form.

## The recipe contract (milestone 2)

The JSON shape of a recipe, exchanged between the API and the page. It is defined once with Pydantic
in [`backend/app/schemas.py`](../backend/app/schemas.py) and mirrored in TypeScript in
[`frontend/src/types.ts`](../frontend/src/types.ts). The API also publishes it as JSON Schema at
`/openapi.json` (browsable at `/docs`), where every field is listed as required because every
response includes it.

```json
{
  "id": 2,
  "title": "עוף בסיר עם אורז",
  "category": { "id": 2, "name": "בישולים" },
  "subcategory": null,
  "servings": "4 מנות",
  "ingredient_groups": [
    { "name": null, "ingredients": [
      { "text": "2 כוסות אורז בסמטי", "quantity": "2 כוסות" },
      { "text": "מלח ופלפל", "quantity": null }
    ] }
  ],
  "step_groups": [
    { "name": "בסיר לחץ", "steps": ["מבשלים 25 דקות מהרגע שהסיר מגיע ללחץ."] },
    { "name": "בסיר רגיל", "steps": ["מבשלים על אש נמוכה כשעה וחצי, עד שהעוף רך."] }
  ],
  "notes": [],
  "sources": [{ "kind": "text", "url": null, "creators": [] }],
  "is_sample": true,
  "created_at": "2026-10-19T08:00:00Z",
  "updated_at": "2026-10-19T08:00:00Z"
}
```

**Reading and writing use different models.** The API returns `Recipe` (above). To create or save,
the page sends `RecipeInput`: the same content fields, plus `category_id` and `subcategory_id`
instead of `category` and `subcategory`. It has no `id`, timestamps or `is_sample`; the server sets
those. A save replaces the whole recipe (`PUT`), sources included.

How it encodes the brief's fidelity rules:

- **Wording as written.** An ingredient line keeps its quantity, unit and state ("150 גרם חמאה מומסת"
  vs "30 גרם חמאה רכה"), and steps keep their wording. Quantities are never numbers, because scaling
  is out of scope.
- **Trimming.** Only spaces and invisible direction marks at the very start and end of a text are
  removed. A real caption's title began with a left-to-right mark, which flipped a Hebrew heading
  to read left to right. Marks inside the text are kept, and text made only of marks counts as empty.
- **`quantity`** is the amount exactly as written, or `null` when the recipe gives none. It must be
  quoted from its own ingredient line, and cannot be cut out of a longer number ("2" from "200 גרם"),
  so it cannot be reworded relative to that line. Whether it is the right part of the line, and
  whether the line matches the source, is checked in review and evaluation (milestones 4 and 7).
  The page shows `null` as "ללא כמות" (no quantity), never as an amount or "to taste".
- **Groups follow the source.**
  - Ingredients are grouped per component.
  - Step groups follow the source's own headings. When the source gives alternative methods as
    separate passages (pressure cooker / regular pot), they become separate step groups named with
    the source's words, so their times never merge.
  - Alternatives written inside one sentence stay one step, because the sentence already keeps
    their times apart.
  - Never invent a heading or a sentence.
- **No free-text categories.** `category` is `null` when unclassified. Otherwise it is a stored
  category's id and name, never free text. A subcategory requires a category.
- **Attribution.** `sources[].creators` lists every creator the source names, main author first
  (collaboration posts have two).
- **Times with a time zone.** `created_at` and `updated_at` must carry a time zone and are sent with
  `Z` (UTC), so the browser shows the right local time.
- **Strict input.** Unknown fields are rejected, so a typo or an invented field fails loudly.
- **Links are web links.** A source `url` must start with `http://` or `https://`, because the page
  shows it as a clickable link (no `javascript:` or `file:` addresses).
- **Samples are marked.** `is_sample` is true for the four invented examples created with a new
  database, and stays true when they are edited. The page labels them.
- **Original source kept apart.** `sources` is editable attribution: where the recipe came from.
  The imported original (caption or page text, screenshots) will be stored in its own table that
  saving a recipe never rewrites (milestone 4).

**Where things go.** These rules guide extraction (milestone 4); they need no schema change:

- **Equipment and pan sizes** mentioned in headings ("תבנית קוטר 20") go into `notes`, word for word.
- **Not part of the recipe:** intros, calls to action, @mentions and hashtags. They stay in the
  source's original text (milestone 4).
- **Heading markers** (a leading `|`, a trailing `:` or `-`) are dropped from group names.
- **A one-line group** of the form "for X - item" becomes a group named X with that item.
- **A missing title** is composed from the source's own words and flagged for review.
- **Headings mid-method:** steps after a heading stay under it until the next heading. No unnamed
  "continuation" groups.
- **An ingredient mentioned only in the steps** (strawberries in one real caption) is flagged for
  review with its source context. It is never added as an ingredient line.

Planned additions, when the features need them: `status` (draft or saved) and `issues` (review
flags with source context), both in milestone 4, where imported drafts first appear.

## Import flow (planned)

1. **Fetch** (importer): URL, text, or images → a *source record* (original text and/or files, URL,
   creators, fetch outcome). If fetching fails, the API returns a specific error code, and the
   frontend keeps the user's input and offers to paste the text or upload screenshots instead.
2. **Extract** (model): source → recipe draft via structured output. The output model is built from
   the contract's *content* fields (title, servings, ingredient groups, step groups, notes) plus
   `issues`. It has no ids, timestamps, sources or category names. A quantity that is not quoted
   word for word becomes `null` plus an issue, rather than rejecting the whole draft. Fields hold the
   original wording. Missing information stays missing. Problems go into `issues`: no quantity
   given, an ingredient only mentioned in the steps (with its source context), unreadable or cut-off
   text, ambiguous alternatives.
3. **Classify** (model, then backend validation): the model may only answer with the ID of an
   existing category or subcategory, or "unresolved". Its output schema has **no free-text category
   field**, so it cannot invent, suggest or name a new one. The backend then:
   - checks the category ID exists and is a top-level category;
   - checks the subcategory belongs to that category;
   - turns anything invalid or ambiguous into *unresolved*, with an issue;
   - **never creates, suggests or names a category.** Only the categories endpoint creates one,
     called from the settings screen or the review screen's explicit "new category" form, where
     the user types the name.
   The model's confidence is not trusted as a probability.
4. **Review**: the draft is saved immediately as `status = draft`, so nothing is lost. The user edits it,
   picks or creates a category, and presses Save. A draft may stay unclassified.

## Data model (milestone 3)

The database is one SQLite file, `<data folder>/recipes.db`. The tables are defined as SQLAlchemy
classes in [`backend/app/models.py`](../backend/app/models.py) and created when the backend starts
(`Base.metadata.create_all`). A new database also gets the three starter categories and the four
sample recipes (`backend/app/seed.py`), once: deleted samples are not added again.

| Table | Columns | Notes |
|---|---|---|
| `categories` | `id`, `name`, `description`, `parent_id` (NULL = top level) | Subcategories are rows whose parent is a top-level category (one level deep). `UNIQUE(id, parent_id)` lets recipes reference the pair. The three starter categories (קינוחים, בישולים, ארוחות קלילות) are created with the database; after that only the user manages categories (milestone 6). |
| `recipes` | `id`, `title`, `category_id`, `subcategory_id`, `servings`, `ingredient_groups` (JSON), `step_groups` (JSON), `notes` (JSON), `is_sample`, `created_at`, `updated_at` | Composite foreign key `(subcategory_id, category_id) → categories(id, parent_id)`, so the database rejects a subcategory under the wrong parent. See the enforcement notes below. Times are stored as UTC. |
| `recipe_sources` | `id`, `recipe_id`, `position`, `kind`, `url`, `creators` (JSON) | Editable attribution, in order. Deleting a recipe deletes its sources; saving replaces them. |

Planned: `status` and `issues` on `recipes` (milestone 4); an `imported_sources` table with the
original text, fetch outcome and time, which saving a recipe never rewrites (milestone 4); and
`source_files` with ordered screenshots, paths relative to the data folder (milestone 5). Adding
columns to an existing database needs a migration, so milestone 4 introduces Alembic.

**Enforcing the category rule in the database, not only in code.** SQLite checks foreign keys
only when `PRAGMA foreign_keys=ON` is set on each connection, and SQLAlchemy does not set it by
default. We set it with a SQLAlchemy `connect` event. Two cases the composite key cannot catch get
their own guards:
- a subcategory with no category: `CHECK (subcategory_id IS NULL OR category_id IS NOT NULL)`;
- a subcategory's ID used as the top-level `category_id`: checked in code.

Milestone 3 tests cover all three cases.

**Ordered recipe content as JSON columns.** Ingredient groups and step groups are stored as JSON
arrays on the recipe row. Their order is the array order, and they are validated by the same Pydantic
models the API uses. A recipe is always loaded and saved as a whole, so this keeps saves simple: no
delete-and-reinsert of child rows, and no position columns to renumber. The cost: SQL cannot easily
query individual ingredients. Search therefore uses the title plus a derived plain-text column.
Real relations (categories, sources, files) stay as proper tables with foreign keys.

## API

| Method and path | Purpose | Status |
|---|---|---|
| `GET /api/health` | Is the backend running? | ✅ milestone 2 |
| `GET /api/recipes` | All recipes, newest first; later with `?q=&category_id=&subcategory_id=&status=` | ✅ milestone 3; filters planned (milestone 6) |
| `GET /api/recipes/{id}` | One recipe; ids are 1 to 2^63−1 | ✅ milestone 3 |
| `POST /api/recipes` | Create from a `RecipeInput`; returns the stored recipe (201) | ✅ milestone 3 |
| `PUT /api/recipes/{id}` | Save: replaces the whole recipe; returns it (200) | ✅ milestone 3 |
| `DELETE /api/recipes/{id}` | Delete with its sources (204, no body) | ✅ milestone 3 |
| `GET /api/categories` | Top-level categories with their subcategories, for the picker | ✅ milestone 3 |
| `POST /api/categories`, `PUT/DELETE /api/categories/{id}` | Manual category management | planned (milestone 6) |
| `POST /api/imports` | Text, URL, or ordered images → source + draft recipe + issues | planned (milestones 4–5) |
| `GET /api/files/{id}` | Serve a stored source image | planned (milestone 5) |

Error codes the page branches on: `recipe_not_found` (404), `invalid_request` (422, with the invalid
fields in `details`), `unknown_category` and `subcategory_not_in_category` (422, with the field in
`details`), and `forbidden_origin` (403).

Every failing response from the app uses one shape (`backend/app/errors.py`), including FastAPI's own
404, 405 and 422 errors and unexpected server errors (500, with no internal details). `/docs`
documents this shape for the recipe endpoints:
`{"error": {"code": "recipe_not_found", "message": "There is no recipe with id 9.", "details": null}}`.
`code` is stable for the page to branch on; `message` is for people; `details` carries extra data,
such as the list of invalid fields. Paths with a trailing slash (`/api/recipes/`) are a 404, not a
redirect; a redirect would send the browser past the Vite proxy.

## Repository layout

```text
.
├── README.md, .gitignore, .gitattributes, .env.example
├── docs/                     brief, architecture (this file), findings
├── backend/                  Python: uv project
│   ├── pyproject.toml, uv.lock, .python-version
│   ├── app/
│   │   ├── main.py           FastAPI app: health check, host check, error handlers, routers
│   │   ├── config.py         settings from the environment and .env (pydantic-settings)
│   │   ├── errors.py         the single error format
│   │   ├── schemas.py        the recipe contract (Pydantic)
│   │   ├── db.py, models.py  SQLAlchemy: engine and sessions; the tables
│   │   ├── crud.py           recipe reads and writes; the category check
│   │   ├── seed.py           creates the tables; fills a new database once
│   │   ├── sample_data.py    the starter categories and the four invented sample recipes
│   │   ├── api/              recipes.py, categories.py: the routes
│   │   ├── importers/        instagram.py (milestone 1); website.py, screenshots.py (milestone 5)
│   │   ├── extraction/       (milestone 4) model client, prompts, output schemas
│   │   └── classification.py (milestone 4) the strict category rule
│   ├── scripts/              probe_instagram.py: live checks, run by hand
│   ├── tests/                pytest: offline, fixtures and in-process API calls only
│   └── evals/                (milestone 7) model-quality evaluation, explicitly invoked
├── frontend/                 React + TypeScript + Vite
│   └── src/                  main.tsx, App.tsx, types.ts, api.ts, editorForm.ts, components/, test/
├── data/                     git-ignored: recipes.db, uploads/, instagram-probe/
└── .github/workflows/        (milestone 7) CI: deterministic checks only
```

## Milestones

| # | Milestone | Main concepts |
|---|---|---|
| 1 | ✅ Instagram feasibility probe ([findings](instagram-feasibility.md)) | Separating fetching from interpretation; capturing raw data so analysis is testable offline |
| 2 | ✅ FastAPI + Vite/React scaffold; recipe contract; sample recipe list and cooking view | React: components, props, lists and keys, `useState`, lifting state up, derived values, a first `useRef`/`useEffect`; RTL basics; API error format |
| 3 | ✅ SQLite + SQLAlchemy models, recipe CRUD, editor; the page loads recipes from the API | Controlled forms, `useEffect` + `fetch` with cleanup, loading and error states, `key` to reset state, focus management; SQL behind the ORM, transactions, constraints |
| 4 | Pasted text → Claude extraction → strict classification → review → save | Structured output, validation, enforcing the category rule in code |
| 5 | Website (JSON-LD first), screenshots (ordered, multimodal), Instagram importer | Fallback paths, file uploads, bounded timeouts; running a browser from a server |
| 6 | Category settings, search and filters, RTL polish, error handling | Composing screens, accessibility, mixed-direction text |
| 7 | Regression tests, evaluation set, GitHub Actions, docs; then Docker if useful | Tests vs live checks vs model evaluation |

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-10-18 | uv manages the Python environment (`uv.lock` pins exact versions) | Reproducible installs. `uv run …` needs no virtualenv activation (activation scripts are a frequent problem in Windows PowerShell). |
| 2026-10-18 | Python 3.14.8, provided by uv (`requires-python >= 3.14.7`) | CPython 3.14.0–3.14.6 make every Playwright call hold memory until the browser connection closes (cpython#152569, playwright-python#3148). |
| 2026-10-18 | Instagram: the logged-out post page in Playwright first; the embed view over HTTP only as a fallback (milestone 5) | Both returned complete captions. The post page carries the current data. The embed view served an older snapshot (lower like counts in the same minute), uses a legacy data shape, and is meant for embedding under Meta's terms ([findings](instagram-feasibility.md)). |
| 2026-10-18 | Importers return the raw caption plus an outcome; recipe interpretation is a separate step | The brief: an LLM receiving a URL is not an importer. This also gives honest "could not be read" errors. |
| 2026-10-19 | One HTTP library: `httpx2` (the maintained fork of HTTPX) | Starlette's test client and the Anthropic SDK (milestone 4) use it. The importer moved over unchanged; its HTTP path was re-checked live on 2026-10-19. |
| 2026-10-19 | JSON field names in snake_case on both sides | One spelling everywhere, with no renaming layer between Pydantic and TypeScript to learn or debug. |
| 2026-10-19 | Ingredients keep the full line plus the quantity as written (or `null`); step groups follow the source's headings | Fidelity first: nothing is rewritten or forced into numbers, and the no-quantity case is explicit and checkable. Tested against the three real captions. |
| 2026-10-19 | Text trims invisible marks at its edges; timestamps need a time zone; sources list every creator | Found by expressing the real captions in the contract (an LRM-led title, a collaboration post) and by planning the SQLite round trip. |
| 2026-10-19 | The Vite proxy instead of CORS, plus `TrustedHostMiddleware` and no trailing-slash redirects | One origin for page and API in development; a foreign host name (DNS rebinding) gets a 400; a redirect would send the browser past the proxy. |
| 2026-10-19 | After a recipe is chosen, keyboard focus stays on its card; the title is scrolled into view only if it is off-screen | Like tabs that switch the panel beside them: keyboard users keep their place in the list, and narrow screens still show the result. |
| 2026-10-19 | Frontend tests with Vitest + Testing Library + jsdom; Oxlint with accessibility rules | Tests use the page as a person does (roles and visible text). Vitest reuses the Vite setup. |
| 2026-10-19 | TypeScript 7 (native compiler), as pinned by the official Vite template | The current default; strict checking is on by default; type-checking and the build verified on this machine. |
| 2026-10-19 | Sample recipes exist twice (backend and frontend) during milestone 2 | Introduces components and state before data fetching (the brief's order). Verified identical by review. Resolved in milestone 3: the frontend copy is now test data only (`src/test/sampleRecipes.ts`). |
| 2026-10-19 | SQLite through the SQLAlchemy 2 ORM; tables created at startup with `create_all`; Alembic from milestone 4 | One local file, no server to run. No migration tool until the first change to an existing table (`status`, `issues`). |
| 2026-10-19 | Ordered recipe content in JSON columns; categories and sources as real tables | A recipe is loaded and saved whole. Relations that the database must enforce (the category rule) get foreign keys. |
| 2026-10-19 | Saving is a full replace (`PUT` with the whole recipe) | The editor always holds the whole recipe, so there are no partial-update rules to get wrong. |
| 2026-10-19 | The four invented samples are seeded once into a new database with `is_sample`, and labeled in the page | The user asked that invented examples be clearly told apart from their own recipes. They can be edited or deleted; deleted samples stay deleted. |
| 2026-10-19 | Changes are accepted only from the notebook page (`Origin` check); Vite always uses port 5173 (`strictPort`) | Stops other websites from changing recipes through the browser. A moved port would make saves fail with 403, so Vite stops instead. |
| 2026-10-19 | `recipe_sources` holds editable attribution only; imported originals get their own table (milestone 4) | Saving replaces the source rows, so anything stored there would be lost on the next edit. The brief requires the original to be kept apart. |
| 2026-10-19 | The editor checks the same rules as the backend before sending (title, quantity quoted from its line, http(s) links); the backend still decides | Messages appear at once, next to the field. Server refusals are mapped back to their form rows through the `loc` path. |
| 2026-10-19 | Delete asks inside the page; leaving unsaved edits asks with the browser's `confirm` (and on tab close) | Delete is the destructive action, so its question stays next to the recipe and is keyboard friendly. The unsaved-changes question can come from any click, so a simple dialog fits. |
| 2026-10-19 | Frontend tests replace `fetch` with an in-memory fake backend (`src/test/fakeApi.ts`) | Tests use the page end to end (load, type, save) and check the exact request bodies, with no server. The real round trip is checked by backend tests and a manual browser check. |

## Known limitations

- **Direction of mixed-language lists.** A content list takes its direction from its first line
  (`dir="auto"`), so a Hebrew list whose first line starts with a Latin brand name (Oreo) is laid out
  left to right. To be fixed in milestone 6: decide the direction once per recipe and let each line
  order its own text.
- **Language of English recipes.** English recipe text inherits the page's `lang="he"`, so screen
  readers may pronounce it with Hebrew rules. A per-recipe language (set at import, milestone 4) will
  set `lang` and `dir` on the recipe.
- **`/docs` needs the internet.** It loads its viewer from cdn.jsdelivr.net; the notebook page does not.
- **Last save wins.** Two tabs editing the same recipe do not see each other's changes; the later
  save replaces the earlier one. A version check could be added if this ever matters.
- **An edited sample stays a sample.** `is_sample` does not change on edit, even if every line is
  replaced. To keep a recipe of your own, create it with "מתכון חדש".
- **No migrations yet.** A database created by an earlier version keeps its old columns. Until
  milestone 4 adds Alembic, starting over means deleting `data/recipes.db` while the backend is stopped.
- **Focus after removing a row.** The removed row's button had the focus, so focus falls back to the
  page. To be improved with the other accessibility work in milestone 6.
- **Quantities are typed by hand** in the editor. Imports (milestone 4) will fill them in, for review.

## Notes for upcoming milestones

- **Milestone 4:**
  - **Alembic first.** Add it before the `status` and `issues` columns, with a first migration that
    matches today's tables, so existing databases are upgraded instead of recreated.
  - **Imported originals in their own table.** Never rewritten by `PUT /api/recipes/{id}`.
  - **Drafts reuse the editor.** An import is saved as a draft at once; review is the editor plus the
    issues list. `RecipeInput` gains `status`.
  - **Classification goes through `crud.check_classification`.** The model's answer is only an id;
    anything that fails the check becomes unresolved.
  - **New endpoints get the `Origin` check automatically** (it is a middleware for every non-GET request).
  - **Versions** current as of 2026-10-18: anthropic 1.15.0.
- **Milestone 5 (Windows):** `uvicorn --reload` (and `fastapi dev`) runs on an event loop that cannot
  start subprocesses. Playwright then fails with an empty `NotImplementedError`. The importer must run
  Playwright in its own thread with `asyncio.run(..., loop_factory=asyncio.ProactorEventLoop)`, or in
  a child process. Both approaches were verified locally by the tooling research.
