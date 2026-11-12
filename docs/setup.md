# Setup and configuration

The [README](../README.md#run-locally-with-ollama) has the short version: run the app with a local
model. This guide has the details: requirements, a full install on Windows, running the servers,
choosing the model, settings and data, privacy, and troubleshooting.

## Requirements

| Tool | Tested version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.13.1 | Manages Python, the virtualenv and the backend dependencies. |
| Python | 3.14.8 | uv downloads it automatically (about 22 MB). 3.14.7 or newer is required: 3.14.0–3.14.6 have an asyncio bug that makes Playwright hold on to memory. |
| [Node.js](https://nodejs.org/) and npm | Node 24.18.0, npm 11.16.0 | For the frontend. Needs Node 22.22.2+ or 24.15+ (`engines` in `frontend/package.json`); the test tools do not run on Node 20 or early 22. |
| Chromium for Playwright | Playwright 1.64.0, Chromium 156.0.8078.4 | For importing Instagram posts (and the Instagram probe). About 330 MB download, about 720 MB on disk. |
| [Ollama](https://ollama.com) | | Optional: the local model. Or use the Claude API (below). |

Exact versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`. Tested together:

- **Backend:** fastapi 0.147.0, uvicorn 0.54.0, pydantic 2.14.1, pydantic-settings 2.16.0,
  sqlalchemy 2.1.5 (with Python's built-in SQLite 3.53.1), alembic 1.20.0, anthropic 1.15.0,
  httpx2 2.14.0, playwright 1.64.0, beautifulsoup4 4.15.0, pillow 13.0.0 (the public copies of uploaded
  pictures), pytest 9.1.1.
- **Frontend:** react 19.3.1, vite 8.3.4, typescript 7.0.2, vitest 5.0.5, @testing-library/react
  16.3.3, jsdom 30.1.3, oxlint 1.88.0.

## Install (tested on Windows 11)

Run each code block from the repository's folder (the one `git clone` created); each one starts with
its own `cd`.

1. **Get the code:** `git clone https://github.com/liansigawi/ai-recipe-extraction-assistant.git`, or
   download it as a ZIP from GitHub and unpack it.
2. **Install uv and Node.js:**
   - Windows: `winget install --id=astral-sh.uv -e` and `winget install --id=OpenJS.NodeJS.LTS -e`
   - macOS / Linux (not tested here): `curl -LsSf https://astral.sh/uv/install.sh | sh`, and Node.js
     from [nodejs.org](https://nodejs.org/)

   Then **close and reopen your terminal app** (in VS Code, restart VS Code completely; a new terminal
   tab is not enough). Check with `uv --version` and `node --version`.
3. **Backend:** create `backend/.venv` with Python 3.14.8 and the exact versions in `backend/uv.lock`:

   ```powershell
   cd backend
   uv sync
   ```

4. **Frontend:** install the exact versions in `frontend/package-lock.json` into `frontend/node_modules`:

   ```powershell
   cd frontend
   npm ci
   ```

5. **For Instagram import:** download Playwright's Chromium once per computer, and again whenever the
   Playwright version in `uv.lock` changes. It is stored outside the project
   (`$env:LOCALAPPDATA\ms-playwright` on Windows). Without it, an Instagram import says that Chromium
   is missing; pasted text and websites work without it.

   ```powershell
   cd backend
   uv run playwright install chromium
   ```

6. **Choose the model** that reads imported text: [below](#choose-how-imported-text-is-read).

`uv run <command>` runs a command inside the backend's environment, so you never need to activate the
virtualenv yourself. In VS Code, choose `backend\.venv\Scripts\python.exe` as the Python interpreter
(Command Palette → *Python: Select Interpreter*) so the editor sees the installed packages.

## Run the app

Use two terminals, both starting in the repository folder:

```powershell
# Terminal 1: the API, restarted automatically when backend code changes
cd backend
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

# Terminal 2: the web page, updated instantly when frontend code changes
cd frontend
npm run dev
```

`--reload-dir app` makes the server watch only the app's code; without it, it would keep scanning the
1,000+ files in `.venv`. Then open:

- **http://localhost:5173**: the notebook page ([user guide](user-guide.md)).
- **http://127.0.0.1:8000/docs**: the API's interactive documentation, generated from the code. Its
  viewer loads from cdn.jsdelivr.net, so it needs an internet connection.
- **http://localhost:5173/api/health**: the same API reached through the page's server, which is how
  the page talks to the backend.

Stop either server with Ctrl+C in its terminal. Start the backend first: if it is not running, the page
says it cannot reach the server and offers "נסו שוב" (try again).

The backend accepts changes only from pages on **http://localhost:5173**, so Vite always uses port 5173.
If something else already uses that port (often an earlier `npm run dev` still running), Vite stops
with "Port 5173 is already in use" instead of moving to another port. Close the other one first.

## Choose how imported text is read

Pasted text, Instagram captions and website text are turned into a draft by a model: a local one through
Ollama, or the Claude API. The setting is `RECIPES_EXTRACTOR` in `.env`: `claude` (the default in
`.env.example`) or `ollama`. The import screen says which one is in use. With neither available, you can
still import: "שמירה בלי עיבוד" (save without processing) keeps the text as a draft for you to fill in.

### Run extraction on this computer (Ollama)

With [Ollama](https://ollama.com), the text never leaves this computer and imports cost nothing. The
backend checks a local model's answers exactly like Claude's, but **expect more points to check**: Qwen3
8B sometimes chooses a wrong category, a quantity without its unit, or keeps an introduction as a note
([extraction-quality.md](extraction-quality.md)). It does not retype the recipe, so it cannot misspell
its words ([how the model reads a recipe](architecture.md#how-the-model-reads-a-recipe)).

1. **Install Ollama:** `winget install --id Ollama.Ollama -e`. It runs a small server on this computer
   only (`127.0.0.1:11434`) and starts with Windows; quit it from its tray icon. Do not change
   `OLLAMA_HOST`: that would open it to your network.
2. **Download a model** (about 5 GB): `ollama pull qwen3:8b`.
3. **Choose it:** copy `.env.example` to `.env` in the repository root (if you have not yet) and set
   `RECIPES_EXTRACTOR=ollama`. No restart is needed. The import button then reads "קריאה עם המודל
   המקומי".

Tested on an RTX 5060 Laptop GPU (8 GB): a long Instagram caption takes 20–30 seconds, a short recipe
6–20 seconds; the first import after a while also loads the model (a few seconds). `ollama ps` shows
whether the model runs on the GPU: `100% GPU` is fast; a CPU share is much slower.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_EXTRACTOR` | `claude` | `ollama`: read imported text with a local model. |
| `RECIPES_OLLAMA_MODEL` | `qwen3:8b` | The Ollama model to use (`ollama list` shows what you have). |
| `RECIPES_OLLAMA_CONTEXT_TOKENS` | `8192` | The model's working memory for one import. 8k fits qwen3:8b entirely in 8 GB and is enough for long captions (one needed about 4,850). For longer texts the import says it ran out; raise it, and part of the model moves to the CPU. |
| `RECIPES_OLLAMA_TIMEOUT_SECONDS` | `300` | The longest one local import waits for the model (all its requests together, in clock time: if the computer sleeps past it, the import stops when it wakes). Then nothing is saved and the page says so; what you pasted or linked stays, to try again. |
| `RECIPES_OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama runs. Only addresses on this computer are accepted. |
| `RECIPES_EXTRACTION_MODE` | `references` | How the model answers ([architecture.md](architecture.md#how-the-model-reads-a-recipe)). `text`: it retypes the recipe, the first approach, kept for comparison. Applies to Claude too. |

To free the space again: `ollama rm qwen3:8b`, and uninstall Ollama like any app.

### Connect the Claude API

"קריאה עם Claude" uses the Claude API, which needs an API key from Anthropic. Each import is one paid
request: a few thousand tokens for a typical recipe. The Claude Console shows your usage and lets you
set a spending limit. The current way of reading recipes has been evaluated with the local model only
([extraction-quality.md](extraction-quality.md)).

1. **Create a key.** Sign in to the Claude Console at https://platform.claude.com, open **API keys**,
   and create a key. It starts with `sk-ant-`. Copy it.
2. **Put it in `.env`, in VS Code.** In the repository root, copy `.env.example` to a new file named
   `.env`, and add this line with your key (no quotes, no spaces):

   ```text
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   Save the file. Type the key into the editor, not into a terminal command: terminals keep a history of
   what you type.
3. **Check that git ignores it.** `git check-ignore -v .env` should print the `.gitignore` line that
   ignores it, and `git status` should not list `.env`.
4. **Use it.** No restart is needed: the backend reads the key at each import. The import screen says
   whether a key is configured (the page is told *whether* there is a key, never the key).

Keep the key to yourself: never paste it into a chat, an issue, a commit or a screenshot. If it leaks,
delete it in the Console and create a new one.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_MODEL` | `claude-opus-5-5` | The Claude model for imports. `claude-sonnet-5-5` is cheaper. |
| `RECIPES_MODEL_TIMEOUT_SECONDS` | `120` | How long one request may take before the import reports a timeout. |

## Settings and where your data lives

Settings use the `RECIPES_` prefix. Set them in `.env` in the repository root (copy `.env.example`,
edit it in VS Code, which saves UTF-8). `.env` is git-ignored. Settings marked in `.env.example` as
read at start-up need a backend restart; a real environment variable wins over `.env`.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_DATA_DIR` | `data/` in the repository | Where the database and other local data are kept. Must be a full path. |
| `RECIPES_SQL_ECHO` | `false` | `true` prints every SQL statement the backend runs, in its terminal. |

The model settings are [above](#choose-how-imported-text-is-read).

All local data goes in one folder, `data/` by default, excluded from git:

- **Recipes:** `<data folder>/recipes.db`, one SQLite file. The backend creates it on its first start,
  with the starter categories and the four invented sample recipes, and prints its location ("Using the
  recipes database at …").
- **Pictures and videos:** `<data folder>/media/`, each file once (named by its content), shared by every
  recipe that uses it. A file is deleted only when no recipe uses it any more.
- **Back up:** stop the backend, then copy **both** `recipes.db` **and** `media/` (or the whole data
  folder). The database says which pictures belong to which recipe; the folder holds the pictures. Restore
  them together: a database without its `media/` folder shows "התמונה לא נמצאה" placeholders.
- **Database upgrades:** when a new version needs a changed database, the backend upgrades it at start-up.
  It first copies the file to `recipes.backup-<date>-<time>-before-<migration>.db` in the same folder, then
  upgrades it in one step that either completes or changes nothing. To go back, stop the backend and put
  the backup copy in place of `recipes.db`. Delete old copies when you no longer need them. Details:
  [architecture.md, "Migrations"](architecture.md#data-model-milestones-3-and-4).
- **Start over:** stop the backend, delete `recipes.db` and `media/`, and start it again: a new database
  with only the categories and samples.
- **Other folders:** Instagram probe runs in `instagram-probe/`, evaluation results in `evals/extraction/`,
  the public copy in `public-notebook/` ([public-notebook.md](public-notebook.md)).

`RECIPES_DATA_DIR` must be a **full path**; a relative path is rejected, because it could put data
somewhere git does not ignore. In `.env`, write paths **with forward slashes and no quotes**
(`RECIPES_DATA_DIR=D:/Backups/recipe-notebook`): inside double quotes, `.env` treats `\r`, `\n` and
similar as special characters, which corrupts Windows paths; the backend refuses such a value with a
hint. In PowerShell:

```powershell
$env:RECIPES_DATA_DIR = "D:\Backups\recipe-notebook"   # this terminal session only
setx RECIPES_DATA_DIR "D:\Backups\recipe-notebook"      # permanently, for terminals opened afterwards
```

## Privacy: what stays on this computer

- Both servers listen on this computer only (`127.0.0.1` / `localhost`), and the API answers only
  requests addressed to those names. The notebook page loads nothing from the internet.
- **With the local model**, imported text is read on this computer and sent nowhere.
- **With the Claude API**, each import sends Anthropic the text it reads (what you pasted, a post's
  caption, or a page's text or recipe data) and your category names and descriptions, and nothing else
  from the notebook. "שמירה בלי עיבוד" sends nothing.
- **The API key stays on this computer**, in the backend's settings. The page never receives it.
- **Importing an Instagram link** contacts Instagram from this computer, as a logged-out visitor:
  instagram.com, and its content hosts (cdninstagram.com, fbcdn.net) to load the post and download its
  pictures and videos. It sends only the post's address and the media addresses the post lists.
- **Importing a website** fetches that one page and its main picture.

## Windows troubleshooting

| Problem | What to do |
|---|---|
| PowerShell says "running scripts is disabled on this system" when you run `npm` | Allow scripts for your user once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then try again. |
| `uv`, `node` or `ollama` is not found right after installing | Close and reopen the terminal (restart VS Code completely). For Ollama you can also use `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`. |
| "Port 5173 is already in use" | An earlier `npm run dev` is still running: close it. The port cannot change (see [Run the app](#run-the-app)). |
| The page says it cannot reach the server | Start the backend (Terminal 1), then press "נסו שוב". |
| An Instagram import says Chromium is missing | `cd backend`, then `uv run playwright install chromium`. |
| Local imports are slow | `ollama ps`: the model should run `100% GPU`. A long text with a larger `RECIPES_OLLAMA_CONTEXT_TOKENS` moves part of it to the CPU. |
| The backend refuses `RECIPES_DATA_DIR` | Use a full path with forward slashes and no quotes in `.env`. |
| Hebrew shows as garbage in PowerShell 5.1 | Open the file in VS Code, or add `-Encoding UTF8` to `Get-Content`. |
| Publishing the public copy fails with "Access is denied" | Stop any running preview of the site first ([public-notebook.md](public-notebook.md#costs-and-limitations)). |
