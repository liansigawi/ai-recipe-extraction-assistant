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
   │                   milestone 3; imports of pasted text, milestone 4
   ├─ crud.py          Reads and writes recipes; checks chosen category ids against the database.
   ├─ models + db      SQLAlchemy ORM over SQLite (data/recipes.db), milestone 3.
   ├─ migrate.py       Brings the database up to date at start-up (Alembic, migrations/), milestone 4.
   ├─ extraction/      Claude API: pasted text → answer in a fixed JSON schema → checked → draft
   │                   with review issues (milestone 4). Classification is part of the same answer:
   │                   only ids of existing categories; the backend checks them. Never creates categories.
   ├─ importers/       FETCH source content only: instagram (milestone 1); website, screenshots
   │                   (planned, milestone 5). No AI.
   └─ files            (planned, milestone 5) Uploaded screenshots under data/uploads/, paths in the database.
          │
          └─► Anthropic API (external, from milestone 4): only the pasted text and the category list.
```

**Responsibilities.** React owns the interface and the user's in-progress input. FastAPI owns
everything that needs trust or secrets: fetching sources, calling the model, validating, classifying,
and saving. The Anthropic API key lives only in the backend's settings (`.env` or the environment).

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

**Review fields (milestone 4).** `status` is `draft` (imported, not reviewed) or `saved`.
`issues` lists what to check, each with a `kind`, a Hebrew `message` and, when it is about specific
words, a `quote` of the original. `original` holds the pasted text exactly as pasted, the model that
read it and when; it is read-only: `RecipeInput` has no such field, so a save cannot change it.

## Import flow (milestone 4: pasted text)

```text
ImportPanel ── POST /api/imports/text {text, use_model} ──► app/api/imports.py
  1. Pydantic: 1 to 20,000 characters, not blank. The text is kept exactly (no trimming).
  2. claude.py: one Messages API request, with structured output (the JSON schema of
     extraction/output.py, category ids limited to the existing ones), a 16,000-token answer
     limit, a timeout (120 s) and two automatic retries for temporary errors.
  3. review.py: checks every part of the answer and builds a draft with issues (below).
  4. crud.create_import: checks the category ids against the database again, then saves the
     draft (status "draft") and the original text in one transaction.          → 201 + the draft
Any failure before step 4 saves nothing; the page keeps the pasted text (also in localStorage).
```

**The pasted text is data, not instructions.** It goes into the user message between tags whose
name ends with a random suffix made for each request, so the text cannot close the tag and pose
as instructions; the system prompt says to ignore requests inside it. The answer can only be the
schema's fields, and is checked like any other answer. Evaluation case 08 tests exactly this.

**The checks in `review.py`** (nothing the model says is taken on trust):
- every title, ingredient line, step, note and group name must appear in the original text (after
  normalizing only spacing, Unicode form and invisible marks); a line that does not is kept, with a
  `not_found_in_source` issue that quotes it;
- every quantity must be written in its own line (`quoted_from`, the contract's rule); otherwise it
  becomes `null` with a `quantity_not_in_line` issue, never an invented amount;
- a title the model composed (no title in the text) gets a `missing_title` issue;
- classification: only `fit = "clear"` with an existing category id (and, if given, one of that
  category's subcategories) classifies. Anything else, including an inconsistent answer, stays
  unclassified with a `classification_unresolved` issue whose message is written by the backend,
  from the database's own category names;
- issue messages from the model that mention categories are dropped, so no text in the draft can
  suggest a new category; quotes that are not in the original are removed;
- the model's own issues (`ingredient_only_in_steps`, `unclear_text`, `missing_information`,
  `ambiguous_alternative`, `multiple_recipes`, `other`) are kept, at most 20.

**Review and explicit save.** The draft opens in the editor with the original text (sticky, so it
stays in view) and the issues; each issue can be marked "handled". "Save as recipe" (a plain
button, never the form's Enter key) sends `status: "saved"` and no issues; "save draft" (the form's
default action) keeps `status: "draft"` and the open issues. A draft may stay unclassified.

**Without the model.** `use_model: false` saves the text as a draft without calling Claude, with a
`not_extracted` issue and the first line as a stand-in title, for the person to fill in. It works
with no API key.

**Not yet:** websites, screenshots and Instagram links (milestone 5) will fetch a source first and
then use the same extraction and checks.

## Data model (milestones 3 and 4)

The database is one SQLite file, `<data folder>/recipes.db`. The tables are defined as SQLAlchemy
classes in [`backend/app/models.py`](../backend/app/models.py), and created and changed by
migrations (below). A new database also gets the three starter categories and the four sample
recipes (`backend/app/seed.py`), once: deleted samples are not added again.

| Table | Columns | Notes |
|---|---|---|
| `categories` | `id`, `name`, `description`, `parent_id` (NULL = top level) | Subcategories are rows whose parent is a top-level category (one level deep). `UNIQUE(id, parent_id)` lets recipes reference the pair. The three starter categories (קינוחים, בישולים, ארוחות קלילות) are created with the database; after that only the user manages categories (milestone 6). |
| `recipes` | `id`, `title`, `category_id`, `subcategory_id`, `servings`, `ingredient_groups` (JSON), `step_groups` (JSON), `notes` (JSON), `is_sample`, `created_at`, `updated_at`, `status`, `issues` (JSON) | Composite foreign key `(subcategory_id, category_id) → categories(id, parent_id)`, so the database rejects a subcategory under the wrong parent. See the enforcement notes below. Times are stored as UTC. `status` is `'draft'` or `'saved'` (a CHECK constraint). |
| `recipe_sources` | `id`, `recipe_id`, `position`, `kind`, `url`, `creators` (JSON) | Editable attribution, in order. Deleting a recipe deletes its sources; saving replaces them. |
| `recipe_imports` | `id`, `recipe_id` (unique), `kind`, `original_text`, `model`, `imported_at` | The imported original, exactly as pasted. Written once, when the import is saved; saving the recipe never touches it; deleting the recipe deletes it. |

Planned: `source_files` with ordered screenshots, paths relative to the data folder, and the fetch
outcome for links (milestone 5).

**Migrations.** Schema changes are Alembic scripts in `backend/migrations/versions/`: `0001`
creates the milestone-3 tables statement for statement (a test compares it with
`tests/fixtures/milestone3_schema.sql`); `0002` adds `status`, `issues` and `recipe_imports`
with `ALTER TABLE ... ADD COLUMN`, which keeps the existing rows in place. At start-up,
`app/migrate.py`:
- creates a new database with every migration, then seeds it;
- recognizes a milestone-3 database (tables but no `alembic_version`) and marks it as `0001`;
- before changing an existing database, copies it with SQLite's backup API to
  `recipes.backup-<UTC time>-before-<revision>.db`;
- runs the migrations in **one transaction** with foreign keys off (SQLite's own procedure: with
  them on, rebuilding a table would cascade-delete rows that point at it), then runs
  `PRAGMA foreign_key_check` and `integrity_check`. Python's `sqlite3` would run `CREATE`/`ALTER`
  outside the transaction, so the migration engine issues `BEGIN` itself; a test shows that without
  this a failed upgrade leaves a half-changed database.

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
| `GET /api/extraction` | Is an API key configured, and which model imports use (never the key) | ✅ milestone 4 |
| `POST /api/imports/text` | Pasted text → a saved draft with review issues and the original (201) | ✅ milestone 4 |
| `POST /api/imports/link`, `/screenshots` | A URL or ordered images → the same draft flow | planned (milestone 5) |
| `GET /api/files/{id}` | Serve a stored source image | planned (milestone 5) |

Error codes the page branches on: `recipe_not_found` (404), `invalid_request` (422, with the invalid
fields in `details`), `unknown_category` and `subcategory_not_in_category` (422, with the field in
`details`), and `forbidden_origin` (403). Imports add `not_a_recipe` (422),
`extraction_not_configured` and `extraction_busy` (503), `extraction_timeout` (504), and
`extraction_auth_failed`, `extraction_unreachable`, `extraction_refused`, `extraction_incomplete`,
`extraction_invalid_output`, `extraction_failed` (502).

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
│   │   ├── migrate.py        upgrades the database at start-up, after a backup
│   │   ├── crud.py           recipe reads and writes; the category check
│   │   ├── seed.py           fills a new database once
│   │   ├── sample_data.py    the starter categories and the four invented sample recipes
│   │   ├── api/              recipes.py, categories.py, imports.py: the routes
│   │   ├── extraction/       output.py (answer schema), prompt.py, claude.py (API call), review.py (checks)
│   │   └── importers/        instagram.py (milestone 1); website.py, screenshots.py (milestone 5)
│   ├── migrations/           Alembic: env.py, versions/0001_milestone_3.py, 0002_imports_and_review.py
│   ├── scripts/              probe_instagram.py: live checks, run by hand
│   ├── tests/                pytest: offline, fixtures and in-process API calls only; never calls Claude
│   └── evals/                the extraction quality check: paid, run by hand; cases/ (invented texts)
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
| 4 | ✅ Pasted text → Claude extraction → strict classification → review → save; migrations | Structured output, validating a model's answer, prompt injection, enforcing the category rule in code; migrations and transactions; `localStorage`; work that finishes after the user moved on |
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
| 2026-10-20 | Alembic migrations, run by the backend at start-up after a backup copy, in one transaction with foreign keys off; milestone-3 databases are stamped at `0001` | The user's database must be kept, never reset. A start-up upgrade needs no extra step; the backup and the all-or-nothing transaction make it safe; tests prove the rollback and that `0001` equals milestone 3's tables. |
| 2026-10-20 | Default model `claude-opus-5-5`, configurable with `RECIPES_MODEL` | The most capable current model, for fidelity on long Hebrew captions. An import is one request, so the cost per recipe stays small; a cheaper model is one setting away. |
| 2026-10-20 | One request per import does extraction and classification together, with structured output whose category ids are an `enum` of the existing ids | One request costs less and is faster than two. The model can only choose an existing id, ambiguity is an explicit answer (`fit`), and the backend still validates everything. |
| 2026-10-20 | `messages.create` with a JSON schema, and our own parsing, rather than the SDK's `messages.parse` | We check the stop reason first (cut off, refused) and turn each case into its own error code; `parse` would fail on a cut-off answer with a generic error. |
| 2026-10-20 | The model's answer schema is lenient; `review.py` turns problems into issues instead of rejecting the answer | One unquotable quantity should not discard a whole recipe. The person sees exactly what to check. |
| 2026-10-20 | Every extracted line is checked against the original text | A cheap, deterministic way to catch invented or reworded content, whatever the model. |
| 2026-10-20 | Classification messages are written by the backend; model messages that mention categories are dropped | The rule is "never suggest a new category": free text from the model could, so it is not shown. |
| 2026-10-20 | A draft is saved only after a successful extraction; on failure the page keeps the text (also in `localStorage`) | Nothing half-made in the database, and nothing lost in the page, even after a reload. |
| 2026-10-20 | "Save as recipe" is a plain button; the form's Enter key saves a draft | Saving a reviewed recipe must be deliberate. |
| 2026-10-20 | The extraction quality check is a separate, explicitly run script with hand-written expectations; real captions stay in `data/` | Paid and model-dependent, so never part of the tests or CI. Third-party captions are not committed. |

## Known limitations

- **Direction of mixed-language lists.** A content list takes its direction from its first line
  (`dir="auto"`), so a Hebrew list whose first line starts with a Latin brand name (Oreo) is laid out
  left to right. To be fixed in milestone 6: decide the direction once per recipe and let each line
  order its own text.
- **Language of English recipes.** English recipe text inherits the page's `lang="he"`, so screen
  readers may pronounce it with Hebrew rules. A per-recipe language will set `lang` and `dir` on the
  recipe (milestone 6, with the other direction work).
- **`/docs` needs the internet.** It loads its viewer from cdn.jsdelivr.net; the notebook page does not.
- **Last save wins.** Two tabs editing the same recipe do not see each other's changes; the later
  save replaces the earlier one. A version check could be added if this ever matters.
- **An edited sample stays a sample.** `is_sample` does not change on edit, even if every line is
  replaced. To keep a recipe of your own, create it with "מתכון חדש".
- **Focus after removing a row or marking an issue handled.** The button had the focus, so focus
  falls back to the page. To be improved with the other accessibility work in milestone 6.
- **The source check is literal.** A line the model shortened (an emoji or a parenthesis dropped
  from the middle) is flagged as not found, although nothing was invented. Better a false alarm than
  a missed change; the quality check reports how often it happens.
- **An import cannot be cancelled.** "ביטול" during an import leaves the page, but the request
  continues and its draft appears in the list when it is ready.
- **One import at a time per page**, and the import screen has a single text box (no multiple
  recipes in one paste: the model takes the main one and flags `multiple_recipes`).

## Notes for upcoming milestones

- **Milestone 5:**
  - **Reuse the extraction.** A fetched caption or page text goes through the same
    `ClaudeExtractor`, `build_draft` and `create_import`; `recipe_imports.kind` gains `instagram`,
    `website` and `screenshots`, plus the URL and fetch outcome (a migration).
  - **Screenshots** are sent as image blocks in the same request, in order; the source check in
    `review.py` cannot compare with an image, so their lines need another review signal.
  - **Add evaluation cases** for each new source kind before relying on it.
- **Milestone 5 (Windows):** `uvicorn --reload` (and `fastapi dev`) runs on an event loop that cannot
  start subprocesses. Playwright then fails with an empty `NotImplementedError`. The importer must run
  Playwright in its own thread with `asyncio.run(..., loop_factory=asyncio.ProactorEventLoop)`, or in
  a child process. Both approaches were verified locally by the tooling research.
