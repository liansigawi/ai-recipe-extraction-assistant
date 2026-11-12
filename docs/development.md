# Development

Install and run the app as in [setup.md](setup.md). How the code is organized:
[architecture.md](architecture.md) (with the [repository layout](architecture.md#repository-layout)).

## Tests and checks

The project keeps three kinds of checks apart, and reports which one was run:

1. **Software tests**: deterministic and offline (the commands below). They prove the parsing, the API
   contract and the interface behavior, not that Instagram, a website or a model works today.
2. **Live importer checks**: the Instagram probe, run by hand against real pages
   ([instagram-feasibility.md](instagram-feasibility.md)); the websites tried are in
   [website-import.md](website-import.md).
3. **Model evaluation**: real model requests on representative recipe texts, compared with expectations
   written by hand. Run explicitly, never in the tests; paid with Claude, free with the local model.
   Method, commands and dated results: [extraction-quality.md](extraction-quality.md).

Backend, from `backend/`:

| Command | What it does |
|---|---|
| `uv run pytest` | Backend tests. No network: the API is called in-process, each test gets its own temporary database, and HTTP, Claude and Ollama are replaced by stand-ins. Your `data/` folder, `.env` and API key are never used. |

Frontend, from `frontend/`:

| Command | What it does |
|---|---|
| `npm test` | Page tests with Vitest in a simulated browser (jsdom), against an in-memory fake API: no server needed. `npx vitest` re-runs on every save. |
| `npm run lint` | Oxlint, including accessibility rules. |
| `npm run build` | Type-checks all TypeScript (`tsc -b`), then builds the production files into `frontend/dist/`. |
| `npm run preview` | Serves the built `dist/` at http://localhost:4173 (opening `dist/index.html` directly shows a blank page). |

The public, read-only copy has its own commands and browser check: [public-notebook.md](public-notebook.md).
Bringing saved recipes up to improved import rules: [maintenance.md](maintenance.md).

## The database

| Command (from `backend/`) | What it does |
|---|---|
| `uv run python -m app.migrate` | Upgrades the database now, after a backup copy (the backend also does it when it starts). |
| `uv run alembic history` | Lists the migrations (`backend/migrations/versions/`). |

How migrations and their backups work: [architecture.md](architecture.md#data-model-milestones-3-and-4).
Where the data lives, and backing it up: [setup.md](setup.md#settings-and-where-your-data-lives).

To look inside the database, stop the backend and open `data/recipes.db` with any SQLite viewer (for
example the "SQLite Viewer" extension in VS Code). The tables are `recipes`, `recipe_sources`,
`recipe_imports` (the original texts), `categories`, `recipe_media` (which picture belongs to which recipe,
in what order) and `media_files` (the files in `data/media/`); ingredient groups and steps are readable
JSON. `RECIPES_SQL_ECHO=true` prints every statement the backend runs.
