# Local Recipe Notebook

A personal recipe notebook that runs on your own computer. The goal: import recipes from Instagram
posts, recipe websites, screenshots, or pasted text; review them; and keep them in a searchable
collection that supports Hebrew and right-to-left text.

> **Status: milestone 2 of 7.** A FastAPI backend and a React + TypeScript frontend run locally. The
> page shows a recipe list and a cooking view built from **four sample recipes**. Nothing can be
> imported or saved yet. Milestone 1 (Instagram feasibility) is documented in
> [docs/instagram-feasibility.md](docs/instagram-feasibility.md). The plan and the recipe data
> contract are in [docs/architecture.md](docs/architecture.md), and the original requirements are
> in [docs/brief.md](docs/brief.md).

## Privacy: what stays on this computer

- Both servers listen on this computer only (`127.0.0.1` / `localhost`), and the API answers only
  requests addressed to those names.
- Local data goes in one folder (`data/` by default, excluded from git). It holds Instagram probe
  runs today; the recipes database (milestone 3) and uploaded screenshots (milestone 5) will go there too.
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
  httpx2 2.14.0, playwright 1.64.0, beautifulsoup4 4.15.0, pytest 9.1.1.
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
  how the page will talk to the backend from milestone 3.

Stop either server with Ctrl+C in its terminal.

In this milestone, the page shows the sample recipes in `frontend/src/sampleRecipes.ts`, and the
backend serves the same samples at `/api/recipes`. The page does not call the API yet; that
connection is milestone 3.

## Commands

Backend, from `backend/`:

| Command | What it does |
|---|---|
| `uv run pytest` | Backend tests. No network: the API is called in-process and HTTP is mocked. |
| `uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000` | Runs the API (see above). |
| `uv run python -m scripts.probe_instagram` | Live Instagram check: the three sample posts × 4 strategies = at most 12 page loads, 10 s apart. It stops at the first sign of rate limiting or a login wall. It prints the run folder, where it saves raw pages and a `summary.md`. |
| `uv run python -m scripts.probe_instagram <url> …` | The same check for up to 10 of your own public post or Reel URLs. |
| `uv run python -m scripts.probe_instagram --analyze <run-id>` | Re-analyzes a saved run offline. Pass the run ID (for example `20261018-135240`) or the run folder. |
| `uv run python -m scripts.probe_instagram --help` | All probe options with their defaults. |

Frontend, from `frontend/`:

| Command | What it does |
|---|---|
| `npm run dev` | Runs the page with instant updates (see above). |
| `npm test` | Component tests with Vitest in a simulated browser (jsdom). Use `npx vitest` to re-run on every save. |
| `npm run build` | Type-checks all TypeScript (`tsc -b`), then builds the production files into `frontend/dist/`. You don't need `dist/` yet; the build proves everything compiles. |
| `npm run preview` | Serves the built `dist/` at http://localhost:4173. Opening `dist/index.html` directly shows a blank page, because the built files must be served. |
| `npm run lint` | Checks the code for common mistakes, including accessibility problems, with Oxlint. |

Open `summary.md` files in VS Code. Windows PowerShell 5.1's `Get-Content` shows Hebrew as garbage
unless you add `-Encoding UTF8`.

## Settings and where data lives

All local data goes in one folder: `data/` at the repository root by default, excluded from git.
Probe runs are saved in `<data folder>/instagram-probe/<run-id>/`. Back up by copying the folder.

Settings use the `RECIPES_` prefix. You can set them in a `.env` file: copy `.env.example` to `.env`
in the repository root and edit it in VS Code, which saves UTF-8. `.env` is git-ignored. Commands
read it when they need a setting; the API itself uses none yet. A real environment variable wins
over `.env`. In PowerShell:

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
│   │   ├── main.py                  the FastAPI app: health check, host check, error handling, routers
│   │   ├── config.py                settings from the environment and .env
│   │   ├── errors.py                the single error format for API responses
│   │   ├── schemas.py               the recipe data contract (Pydantic models)
│   │   ├── sample_data.py           the sample recipes (milestone 2 only)
│   │   ├── api/recipes.py           GET /api/recipes and /api/recipes/{id}
│   │   └── importers/instagram.py   Instagram URL parsing, page capture, caption analysis
│   ├── scripts/probe_instagram.py   bounded live probe and offline analysis
│   └── tests/                       pytest: API, contract, importer, probe, settings, code hygiene
├── frontend/                        React + TypeScript + Vite
│   ├── index.html                   the page shell: lang="he" dir="rtl"
│   ├── package.json, package-lock.json, vite.config.ts, tsconfig*.json, .oxlintrc.json
│   └── src/
│       ├── main.tsx                 starts React and renders <App>
│       ├── App.tsx                  page layout; holds the selected-recipe state
│       ├── types.ts                 the recipe contract in TypeScript
│       ├── sampleRecipes.ts         the sample recipes (milestone 2 only)
│       ├── index.css                styles (right-to-left aware)
│       ├── components/              RecipeList, RecipeCard, CategoryChip, RecipeView
│       └── *.test.ts(x), test/      Vitest + Testing Library tests and their setup
└── data/                            local data (git-ignored)
```
