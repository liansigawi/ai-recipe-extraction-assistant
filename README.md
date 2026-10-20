# Local Recipe Notebook

A personal recipe notebook that runs on your own computer. The goal: import recipes from Instagram
posts, recipe websites, screenshots, or pasted text; review them; and keep them in a searchable
collection that supports Hebrew and right-to-left text.

> **Status: milestone 3 of 7.** A FastAPI backend with a SQLite database and a React + TypeScript
> frontend run locally. You can **create, edit and delete recipes** by hand, and they are saved on
> this computer. A new database starts with three categories and **four invented sample recipes**,
> labeled "דוגמה". Importing (from text, websites, screenshots or Instagram) comes in milestones 4–5.
> Milestone 1 (Instagram feasibility) is documented in
> [docs/instagram-feasibility.md](docs/instagram-feasibility.md). The plan and the recipe data
> contract are in [docs/architecture.md](docs/architecture.md), and the original requirements are
> in [docs/brief.md](docs/brief.md).

## Privacy: what stays on this computer

- Both servers listen on this computer only (`127.0.0.1` / `localhost`), and the API answers only
  requests addressed to those names.
- Local data goes in one folder (`data/` by default, excluded from git). It holds the recipes
  database (`recipes.db`) and Instagram probe runs; uploaded screenshots (milestone 5) will go there too.
- The notebook page loads nothing from the internet. The API documentation page (`/docs`) loads its
  viewer from cdn.jsdelivr.net, so it needs an internet connection.
- **This will not be a fully offline app.** From milestone 4, recipe text and images that you submit
  for AI extraction will be sent to the Anthropic API.
- The Instagram probe (and the importer, from milestone 5) contacts Instagram's servers directly from
  this computer: instagram.com, plus its content hosts (cdninstagram.com, fbcdn.net) when a browser is used.

## Requirements

| Tool | Tested version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.13.1 | Manages Python, the virtualenv and the backend dependencies. |
| Python | 3.14.8 | uv downloads it automatically (about 22 MB). 3.14.7 or newer is required: 3.14.0–3.14.6 have an asyncio bug that makes Playwright hold on to memory. |
| [Node.js](https://nodejs.org/) and npm | Node 24.18.0, npm 11.16.0 | For the frontend. Needs Node 24.15+ or 22.22.2+ (the test tools do not run on Node 20 or early 22). |
| Chromium for Playwright | Playwright 1.64.0, Chromium 156.0.8078.4 | Only for the Instagram probe. About 330 MB download, about 720 MB on disk. |

Exact versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`. Tested together:

- **Backend:** fastapi 0.147.0, uvicorn 0.54.0, pydantic 2.14.1, pydantic-settings 2.16.0,
  sqlalchemy 2.1.5 (with Python's built-in SQLite 3.53.1), httpx2 2.14.0, playwright 1.64.0,
  beautifulsoup4 4.15.0, pytest 9.1.1.
- **Frontend:** react 19.3.1, vite 8.3.4, typescript 7.0.2, vitest 5.0.5, @testing-library/react
  16.3.3, jsdom 30.1.3, oxlint 1.88.0.

## Setup (tested on Windows 11)

Run each code block from the repository folder (for example `C:\Projects\Recipes`); each one starts
with its own `cd`.

1. Install uv and Node.js:
   - Windows: `winget install --id=astral-sh.uv -e` and `winget install --id=OpenJS.NodeJS.LTS -e`
   - macOS / Linux (not tested here): `curl -LsSf https://astral.sh/uv/install.sh | sh`, and Node.js
     from [nodejs.org](https://nodejs.org/)

   Then **close and reopen your terminal app**. If you use VS Code's built-in terminal, restart VS
   Code completely; a new terminal tab is not enough. Check with `uv --version` and `node --version`.

   **If PowerShell says "running scripts is disabled on this system"** when you run `npm`, allow
   scripts for your user account once, then try again:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

2. Backend: create `backend/.venv` with Python 3.14.8 and the exact versions in `backend/uv.lock`:

   ```bash
   cd backend
   uv sync
   ```

3. Frontend: install the exact versions in `frontend/package-lock.json` into `frontend/node_modules`:

   ```bash
   cd frontend
   npm ci
   ```

4. Optional, only for the Instagram probe: download Playwright's Chromium once per computer, and
   again whenever the Playwright version in `uv.lock` changes. It is stored outside the project, in
   `$env:LOCALAPPDATA\ms-playwright` on Windows.

   ```bash
   cd backend
   uv run playwright install chromium
   ```

`uv run <command>` runs a command inside the backend's environment, so you never need to activate
the virtualenv yourself. In VS Code, choose `backend\.venv\Scripts\python.exe` as the Python
interpreter (Command Palette → *Python: Select Interpreter*) so the editor sees the installed packages.

## Run the app

Use two terminals, both starting in the repository folder:

```bash
# Terminal 1: the API, restarted automatically when backend code changes
cd backend
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

# Terminal 2: the web page, updated instantly when frontend code changes
cd frontend
npm run dev
```

`--reload-dir app` makes the server watch only our code; without it, it would keep scanning the
1,000+ files in `.venv`. Then open:

- **http://localhost:5173**: the notebook page.
- **http://127.0.0.1:8000/docs**: the API's interactive documentation, generated from the code.
  You can call each endpoint from there.
- **http://localhost:5173/api/health**: the same API reached through the page's server. This is
  how the page talks to the backend.

Stop either server with Ctrl+C in its terminal. Start the backend first: if it is not running, the
page says it cannot reach the server and offers "נסו שוב" (try again).

The page only accepts changes from **http://localhost:5173**, so Vite always uses port 5173. If
something else already uses that port (often an earlier `npm run dev` still running), Vite stops
with "Port 5173 is already in use" instead of moving to another port. Close the other one first.

### What you can do in the page

- **Browse:** the list shows every recipe, newest first; click a card to open it.
- **Create:** "מתכון חדש" opens an empty form. Only the title is required. Type each ingredient
  line as written, and copy its amount into the quantity box ("200 גרם" from "200 גרם קמח"); leave
  the quantity empty when the recipe gives none. The form refuses a quantity that is not in its line.
- **Edit:** "עריכה" opens the recipe in the same form. Rows can be added, moved (▲ ▼) and removed (✕).
  The category list offers only existing categories, or "לא מסווג" (not classified).
- **Delete:** "מחיקה" asks first, in the page. Deleting cannot be undone.
- Leaving the form with unsaved changes (another recipe, cancel, closing the tab) asks first.

The four samples were invented for this project and are not based on real recipes or on the
Instagram links. They are labeled "דוגמה" in the list and the recipe view. You can edit or delete them;
once deleted, they are not added again.

### Check that recipes are kept after a restart

1. Create a recipe, and edit another one (for example, change a sample's title). Note the time in
   "עודכן" (last saved) under the title.
2. Stop both servers with Ctrl+C, then start them again with the same commands.
3. Reload http://localhost:5173. The new recipe and the edit are still there, with the same "עודכן" time.

You can also look inside the database while the backend is stopped, with any SQLite viewer (for
example the "SQLite Viewer" extension in VS Code): `data/recipes.db` has the tables `recipes`,
`recipe_sources` and `categories`. The ingredient groups and steps are stored as readable JSON.

## Commands

Backend, from `backend/`:

| Command | What it does |
|---|---|
| `uv run pytest` | Backend tests. No network: the API is called in-process, each test gets its own temporary database, and HTTP is mocked. Your `data/` folder is never touched. |
| `uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000` | Runs the API (see above). |
| `uv run python -m scripts.probe_instagram` | Live Instagram check: the three sample posts × 4 strategies = at most 12 page loads, 10 s apart. It stops at the first sign of rate limiting or a login wall. It prints the run folder, where it saves raw pages and a `summary.md`. |
| `uv run python -m scripts.probe_instagram <url> …` | The same check for up to 10 of your own public post or Reel URLs. |
| `uv run python -m scripts.probe_instagram --analyze <run-id>` | Re-analyzes a saved run offline. Pass the run ID (for example `20261018-135240`) or the run folder. |
| `uv run python -m scripts.probe_instagram --help` | All probe options with their defaults. |

Frontend, from `frontend/`:

| Command | What it does |
|---|---|
| `npm run dev` | Runs the page with instant updates (see above). |
| `npm test` | Page tests with Vitest in a simulated browser (jsdom), against an in-memory fake API, so no server is needed. Use `npx vitest` to re-run on every save. |
| `npm run build` | Type-checks all TypeScript (`tsc -b`), then builds the production files into `frontend/dist/`. You don't need `dist/` yet; the build proves everything compiles. |
| `npm run preview` | Serves the built `dist/` at http://localhost:4173. Opening `dist/index.html` directly shows a blank page, because the built files must be served. |
| `npm run lint` | Checks the code for common mistakes, including accessibility problems, with Oxlint. |

Open `summary.md` files in VS Code. Windows PowerShell 5.1's `Get-Content` shows Hebrew as garbage
unless you add `-Encoding UTF8`.

## Settings and where data lives

All local data goes in one folder: `data/` at the repository root by default, excluded from git.

- **Recipes:** `<data folder>/recipes.db`, one SQLite file. The backend creates it on its first
  start, with the starter categories and the sample recipes, and prints its location in the terminal
  ("Using the recipes database at …").
- **Back up:** stop the backend, then copy `recipes.db` (or the whole folder).
- **Start over:** stop the backend, delete `recipes.db`, and start the backend again. You get a new
  database with only the categories and samples. Everything you created is gone.
- **Probe runs:** `<data folder>/instagram-probe/<run-id>/`.

Settings use the `RECIPES_` prefix. You can set them in a `.env` file: copy `.env.example` to `.env`
in the repository root and edit it in VS Code, which saves UTF-8. `.env` is git-ignored. The backend
reads it when it starts. A real environment variable wins over `.env`.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_DATA_DIR` | `data/` in the repository | Where the database and other local data are kept. |
| `RECIPES_SQL_ECHO` | `false` | `true` prints every SQL statement the backend runs, in its terminal. Useful for learning what the ORM does. |

In PowerShell:

```powershell
$env:RECIPES_DATA_DIR = "D:\Backups\recipe-notebook"   # this terminal session only
setx RECIPES_DATA_DIR "D:\Backups\recipe-notebook"      # permanently, for terminals opened afterwards
```

`RECIPES_DATA_DIR` must be a **full path**; a relative path is rejected, because it could put data
somewhere git does not ignore. In `.env`, write paths **with forward slashes and no quotes**
(`RECIPES_DATA_DIR=D:/Backups/recipe-notebook`). Inside double quotes, `.env` treats `\r`, `\n` and
similar as special characters, which corrupts Windows paths; the backend refuses such a value with a hint.

## Three kinds of checks

The project keeps these separate and reports which one was run:

1. **Software tests** (`uv run pytest`, `npm test`): deterministic and offline. They prove the
   parsing, the API contract, and the interface behavior, not that Instagram works today.
2. **Live importer checks** (`scripts/probe_instagram.py`): run by hand against real Instagram pages.
   Results are recorded with dates in [docs/instagram-feasibility.md](docs/instagram-feasibility.md).
3. **Model-quality evaluation** (milestone 7): will compare AI extraction against checked
   expectations. Run explicitly; bounded; uses paid API calls.

## Repository layout (so far)

```text
.
├── README.md, .gitignore, .gitattributes, .env.example
├── docs/
│   ├── brief.md                     original requirements
│   ├── architecture.md              plan, recipe contract, API, milestones, decisions
│   └── instagram-feasibility.md     milestone 1 findings
├── backend/                         Python: uv project
│   ├── pyproject.toml, uv.lock, .python-version
│   ├── app/
│   │   ├── main.py                  the FastAPI app: startup, host and origin checks, error handling, routers
│   │   ├── config.py                settings from the environment and .env
│   │   ├── errors.py                the single error format for API responses
│   │   ├── schemas.py               the recipe data contract (Pydantic models)
│   │   ├── db.py                    the database connection and sessions (SQLAlchemy)
│   │   ├── models.py                the database tables
│   │   ├── crud.py                  reading and writing recipes; the category check
│   │   ├── seed.py                  creates the tables; fills a new database once
│   │   ├── sample_data.py           the starter categories and the four invented sample recipes
│   │   ├── api/                     recipes.py (create, read, save, delete), categories.py (read)
│   │   └── importers/instagram.py   Instagram URL parsing, page capture, caption analysis
│   ├── scripts/probe_instagram.py   bounded live probe and offline analysis
│   └── tests/                       pytest: API, persistence, contract, importer, probe, settings, code hygiene
├── frontend/                        React + TypeScript + Vite
│   ├── index.html                   the page shell: lang="he" dir="rtl"
│   ├── package.json, package-lock.json, vite.config.ts, tsconfig*.json, .oxlintrc.json
│   └── src/
│       ├── main.tsx                 starts React and renders <App>
│       ├── App.tsx                  loads the notebook from the API; what is shown; save and delete
│       ├── api.ts                   every call to the backend, and its error messages
│       ├── editorForm.ts            the editor's form state, checks and conversions (no React)
│       ├── types.ts                 the recipe contract in TypeScript
│       ├── labels.ts                display names, e.g. for source kinds
│       ├── index.css                styles (right-to-left aware)
│       ├── components/              RecipeList, RecipeCard, RecipeView, RecipeActions, RecipeEditor
│       │                            (with IngredientsEditor, StepsEditor, RowButtons, FieldError), CategoryChip
│       ├── test/                    test setup, the fake API, sample recipes as test data
│       └── *.test.ts(x)             Vitest + Testing Library tests
└── data/                            local data (git-ignored)
```
