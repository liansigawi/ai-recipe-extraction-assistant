# Architecture and plan

The plan for the Local Recipe Notebook. The requirements are in [brief.md](brief.md). Items marked
*planned* are decided directionally and get finalized, with tests, in the milestone that builds them.

## Overview

```text
Browser: React + TypeScript (Vite dev server, http://localhost:5173)
   │  fetch("/api/...") JSON          (in development Vite forwards /api to the backend)
   ▼
FastAPI backend (uvicorn, bound to 127.0.0.1:8000)
   ├─ api/             REST routes: imports, recipes, categories. Pydantic in, Pydantic out.
   ├─ importers/       FETCH source content only: instagram, website, screenshots, text. No AI.
   ├─ extraction/      Claude API: source → structured RecipeDraft, validated with Pydantic.
   ├─ classification   Checks model-chosen category IDs against the database. Never creates categories.
   ├─ models + db      SQLAlchemy ORM over SQLite (data/recipes.db).
   └─ files            Uploaded screenshots stored under data/uploads/, paths kept in the database.
          │
          └─► Anthropic API (external): only text/images sent for extraction and classification.
```

**Responsibilities.** React owns the interface and the user's in-progress input. FastAPI owns
everything that needs trust or secrets: fetching sources, calling the model, validating, classifying,
and saving. The Anthropic API key lives only in the backend's environment.

**Local means local.** Both servers run on this computer. Data stays in `data/` (or
`RECIPES_DATA_DIR`). The exception: content you submit for AI extraction is sent to Anthropic. The
README and the import screen say so.

## Import flow (planned)

1. **Fetch** (importer): URL, text, or images → a *source record* (original text and/or files, URL,
   creator, fetch outcome). If fetching fails, the API returns a specific error code, and the
   frontend keeps the user's input and offers to paste the text or upload screenshots instead.
2. **Extract** (model): source → `RecipeDraft` via structured output. Fields hold the original
   wording. Missing information stays missing. Problems go into an `issues` list: no quantity given,
   ingredient only mentioned in the steps (with its source context), unreadable or cut-off text,
   ambiguous alternatives.
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

## Data model (planned, milestone 3)

| Table | Key columns | Notes |
|---|---|---|
| `categories` | `id`, `name`, `description`, `parent_id` (NULL = top level) | Subcategories are rows whose parent is a top-level category (one level deep). `UNIQUE(id, parent_id)` lets recipes reference the pair. The three starter categories (קינוחים, בישולים, ארוחות קלילות) are created once with the database; after that only the user manages categories. |
| `recipes` | `id`, `title`, `status`, `category_id`, `subcategory_id`, `ingredient_groups` (JSON), `steps` (JSON), `notes` (JSON), `issues` (JSON), `created_at`, `updated_at` | Composite foreign key `(subcategory_id, category_id) → categories(id, parent_id)`, so the database rejects a subcategory under the wrong parent. See the enforcement notes below. |
| `sources` | `id`, `recipe_id`, `kind`, `url`, `creator`, `original_text`, `fetch_outcome`, `fetched_at` | The original content, kept apart from the editable recipe. |
| `source_files` | `id`, `source_id`, `position`, `path`, `mime_type`, `size_bytes`, `sha256` | Ordered screenshots. `path` is relative to the data folder. |

**Enforcing the category rule in the database, not only in code.** SQLite checks foreign keys
only when `PRAGMA foreign_keys=ON` is set on each connection, and SQLAlchemy does not set it by
default. We set it with a SQLAlchemy `connect` event. Two cases the composite key cannot catch get
their own guards:
- a subcategory with no category: `CHECK (subcategory_id IS NULL OR category_id IS NOT NULL)`;
- a subcategory's ID used as the top-level `category_id`: checked in code.

Milestone 3 tests cover all three cases.

**Ordered recipe content as JSON columns.** Ingredient groups and steps are stored as JSON arrays on
the recipe row. Their order is the array order, and they are validated by the same Pydantic models
the API uses. A recipe is always loaded and saved as a whole, so this keeps saves simple: no
delete-and-reinsert of child rows, and no position columns to renumber. The cost: SQL cannot easily
query individual ingredients. Search therefore uses the title plus a derived plain-text column.
Real relations (categories, sources, files) stay as proper tables with foreign keys.

## API (planned)

| Method and path | Purpose |
|---|---|
| `POST /api/imports` | Text, URL, or ordered images → source + draft recipe + issues |
| `GET /api/recipes?q=&category_id=&subcategory_id=&status=` | Search and filter |
| `GET /api/recipes/{id}`, `PUT /api/recipes/{id}`, `DELETE /api/recipes/{id}` | Read, edit/save, delete |
| `GET/POST /api/categories`, `PUT/DELETE /api/categories/{id}` | Manual category management |
| `GET /api/files/{id}` | Serve a stored source image |

Errors always use one shape:
`{"error": {"code": "instagram_login_required", "message": "...", "details": {...}}}`.

## Repository layout

```text
.
├── README.md                 setup, commands, tested versions
├── .gitignore                excludes data/, .env, virtualenvs, node_modules
├── .env.example              (milestone 2+) settings without secrets
├── docs/                     brief, architecture (this file), findings
├── backend/                  Python: uv project
│   ├── pyproject.toml, uv.lock, .python-version
│   ├── app/
│   │   ├── config.py         settings from environment
│   │   ├── importers/        instagram.py (milestone 1); website.py, screenshots.py (milestone 5)
│   │   ├── main.py           (milestone 2) FastAPI app
│   │   ├── api/              (milestone 3+) routers
│   │   ├── db.py, models.py, schemas.py   (milestone 3)
│   │   ├── extraction/       (milestone 4) model client, prompts, output schemas
│   │   └── classification.py (milestone 4) the strict category rule
│   ├── scripts/              probe_instagram.py: live checks, run by hand
│   ├── tests/                pytest: offline, fixtures only
│   └── evals/                (milestone 7) model-quality evaluation, explicitly invoked
├── frontend/                 (milestone 2) React + TypeScript + Vite
│   └── src/  components/, pages/, api/, styles/
├── data/                     git-ignored: recipes.db, uploads/, instagram-probe/
└── .github/workflows/        (milestone 7) CI: deterministic checks only
```

## Milestones

| # | Milestone | Main concepts |
|---|---|---|
| 1 | ✅ Instagram feasibility probe ([findings](instagram-feasibility.md)) | Separating fetching from interpretation; capturing raw data so analysis is testable offline |
| 2 | Scaffold FastAPI + Vite/React. Sample recipe view and recipe list. | React: components, props, rendering lists, first `useState`; RTL basics |
| 3 | SQLite + SQLAlchemy models, Pydantic schemas, recipe CRUD, editor | Controlled forms, `useEffect` + `fetch`, loading and error states; SQL behind the ORM |
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

## Notes for upcoming milestones

- **Milestone 2:** current versions as of 2026-10-18 are fastapi 0.143.5, uvicorn 0.54.0,
  sqlalchemy 2.1.5, anthropic 1.15.0, vite 8.3.4 and react 19.3.1. The create-vite React template pins
  TypeScript ~6.0 even though 7.0 is the npm default. The Anthropic SDK and Starlette's test client now
  use `httpx2`, the maintained fork of HTTPX, so the backend should settle on one HTTP library.
- **Milestone 5 (Windows):** `uvicorn --reload` (and `fastapi dev`) runs on an event loop that cannot
  start subprocesses. Playwright then fails with an empty `NotImplementedError`. The importer must run
  Playwright in its own thread with `asyncio.run(..., loop_factory=asyncio.ProactorEventLoop)`, or in
  a child process. Both approaches were verified locally by the tooling research.
