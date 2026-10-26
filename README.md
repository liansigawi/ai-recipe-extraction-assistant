# Local Recipe Notebook

A personal recipe notebook that runs on your own computer. The goal: import recipes from Instagram
posts, recipe websites, screenshots, or pasted text; review them; and keep them in a searchable
collection that supports Hebrew and right-to-left text.

> **Status: milestone 5 of 7, in progress.** A FastAPI backend with a SQLite database and a React +
> TypeScript frontend run locally. You can **paste recipe text or an Instagram post's link** and have
> a model (a local one through Ollama, or Claude) turn it into a draft, review the draft beside the
> original text, and save it explicitly; or create, edit and delete recipes by hand. A new database
> starts with four categories and **four invented sample recipes**, labeled "דוגמה". Importing from
> websites and screenshots comes later in milestone 5.
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
- **What is sent to Anthropic.** When you press "קריאה עם Claude" on the import screen, the text
  you pasted and the list of your category names and descriptions are sent to the Anthropic API.
  Nothing else from the notebook is sent, and "שמירה בלי עיבוד" (save without processing) sends
  nothing. From milestone 5, screenshots you submit will be sent the same way.
- **Or nothing at all:** with a local model ([Run extraction on this computer](#run-extraction-on-this-computer-ollama)),
  the text is read on this computer and is not sent anywhere. The import screen says which one is in use.
- **The API key stays on this computer**, in the backend's settings. The page never receives it.
- **Importing an Instagram link** (and the probe) contacts Instagram's servers directly from this
  computer: instagram.com, plus its content hosts (cdninstagram.com, fbcdn.net) when a browser is used.
  It sends only the post's address, as a logged-out visitor. The caption it reads is then handled like
  pasted text: read on this computer by a local model, or sent to Anthropic with Claude.

## Requirements

| Tool | Tested version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.13.1 | Manages Python, the virtualenv and the backend dependencies. |
| Python | 3.14.8 | uv downloads it automatically (about 22 MB). 3.14.7 or newer is required: 3.14.0–3.14.6 have an asyncio bug that makes Playwright hold on to memory. |
| [Node.js](https://nodejs.org/) and npm | Node 24.18.0, npm 11.16.0 | For the frontend. Needs Node 24.15+ or 22.22.2+ (the test tools do not run on Node 20 or early 22). |
| Chromium for Playwright | Playwright 1.64.0, Chromium 156.0.8078.4 | Only for the Instagram probe. About 330 MB download, about 720 MB on disk. |

Exact versions are pinned in `backend/uv.lock` and `frontend/package-lock.json`. Tested together:

- **Backend:** fastapi 0.147.0, uvicorn 0.54.0, pydantic 2.14.1, pydantic-settings 2.16.0,
  sqlalchemy 2.1.5 (with Python's built-in SQLite 3.53.1), alembic 1.20.0, anthropic 1.15.0,
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

### Import a recipe from pasted text

Needs an API key: see [Connect the Claude API](#connect-the-claude-api). Without one, you can still
save the text as a draft and fill it in yourself.

1. **"ייבוא מתכון"** (import a recipe): paste a recipe into **"טקסט המתכון"**, for example an
   Instagram caption or text copied from a website, and press **"קריאה עם Claude"** (or **"קריאה עם
   המודל המקומי"**). It usually takes less than a minute.
2. The draft opens for **review**. At the top is the original text exactly as you pasted it (it
   stays in view while you scroll), then the points to check, then the editable form:
   - lines that Claude could not copy exactly from the text, quantities that are not written in
     their line (left empty), an ingredient that only the steps mention (not added), missing or
     unclear information;
   - the category: Claude may only pick one of your existing categories. When it is not clear, the
     recipe stays "לא מסווג" (not classified), with an explanation. Nothing ever creates a category.
3. Fix what needs fixing and mark each point **"טופל"** (handled). Then:
   - **"שמירה כמתכון"** (save as recipe) saves it as a recipe. Only this button does that; Enter
     in a field never does.
   - **"שמירת טיוטה"** (save draft) keeps it as a draft, with the points still open, to continue
     later. Drafts are marked "טיוטה" in the list.

The original text is stored with the recipe and never changes when you edit it; open
"הטקסט המקורי" (the original text) in the recipe view to see it.

If anything fails (no internet, Claude busy, no API key), nothing is saved and your text stays in
the box, even after a reload: it is kept in this browser until an import succeeds. You can try
again, or press **"שמירה בלי עיבוד"** (save without processing) to keep the text as a draft and fill
in the recipe yourself.

The four samples were invented for this project and are not based on real recipes or on the
Instagram links. They are labeled "דוגמה" in the list and the recipe view. You can edit or delete them;
once deleted, they are not added again.

### Import a recipe from an Instagram link

1. **"ייבוא מתכון"**, paste the address of a public post or Reel into **"קישור לפוסט באינסטגרם"**
   (for example `https://www.instagram.com/p/DPbKEn-CnUt/`; `/reel/...` addresses and addresses with
   `?igsh=...` work too), and press **"ייבוא מהקישור"**. It usually takes under a minute: a few
   seconds to read the post, then the same extraction as for pasted text (with Ollama, on this computer).
2. The draft opens for review exactly like a pasted one. "הטקסט המקורי" says it is the post's
   caption, links to the post, and shows the full caption exactly as read. The recipe's source is the
   post with its author (and co-authors), which you can edit; the caption and the address stored with
   the original never change.

How the caption is read: as a logged-out visitor. A fresh browser loads the post page and reads the
post's own data, which holds the complete caption. Only if that gives no caption (and Instagram did not
say the post is unavailable or ask to wait) is the post's public embed view fetched once over plain
HTTP. A preview that may be cut off is never imported as if it were complete.

**When the post cannot be read**, nothing is saved, and the page says why: Instagram says the post
isn't available (deleted, private, or temporarily), asks to log in, asks to wait before reading more
posts, the post has no caption, or the page did not answer in time. The link stays in its field: copy
the caption from the post, paste it into the text box below and import it from there. The link is
kept with the recipe as its source.

**When only a preview of the caption was read** (it may be cut off), it is put into the text box with
a warning. Compare it with the post and complete it; if you import it unchanged, the draft carries the
point "כיתוב חלקי" (partial caption). The same happens with a caption in which the model found no recipe:
it is put into the text box (the page asks before replacing other text there), so you can try again or
save it without processing.

What it never does: log in, use your browser's cookies, disguise itself, or retry in loops. It reads
one post that you paste, at human pace. Private posts and posts Instagram shows only to logged-in
visitors cannot be read. Share links (`instagram.com/share/...`) are not supported yet: open them and
copy the post's address. Instagram can change its pages at any time; pasting the caption always works.

### Check that recipes are kept after a restart

1. Create a recipe, and edit another one (for example, change a sample's title). Note the time in
   "עודכן" (last saved) under the title.
2. Stop both servers with Ctrl+C, then start them again with the same commands.
3. Reload http://localhost:5173. The new recipe and the edit are still there, with the same "עודכן" time.

You can also look inside the database while the backend is stopped, with any SQLite viewer (for
example the "SQLite Viewer" extension in VS Code): `data/recipes.db` has the tables `recipes`,
`recipe_sources`, `recipe_imports` (the original texts) and `categories`. The ingredient groups and
steps are stored as readable JSON.

## Connect the Claude API

Importing with "קריאה עם Claude" uses the Claude API, which needs an API key from Anthropic. Each
import is one paid request: a few thousand tokens for a typical recipe. The Claude Console shows
your usage, and lets you set a spending limit.

1. **Create a key.** Sign in to the Claude Console at https://platform.claude.com, open
   **API keys**, and create a key. It starts with `sk-ant-`. Copy it.
2. **Put it in `.env`, in VS Code.** In the repository folder (next to this README), copy
   `.env.example` to a new file named `.env`, and add this line with your key (no quotes, no spaces):

   ```text
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   Save the file. Type the key into the editor, not into a terminal command: terminals keep a
   history of what you type.
3. **Check that git ignores it.** `git check-ignore -v .env` should print the `.gitignore` line that
   ignores it, and `git status` should not list `.env`.
4. **Use it.** No restart is needed: the backend reads the key at each import. The import screen
   says whether a key is configured (the page is told *whether* there is a key, never the key).

Keep the key to yourself: never paste it into a chat, an issue, a commit or a screenshot. If it
leaks, delete it in the Console and create a new one.

Optional settings, also in `.env`:

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_MODEL` | `claude-opus-5-5` | The Claude model for imports. `claude-sonnet-5-5` is cheaper. |
| `RECIPES_MODEL_TIMEOUT_SECONDS` | `120` | How long one request may take before the import reports a timeout. |

## Run extraction on this computer (Ollama)

Instead of Claude, a local model can read imported text, with [Ollama](https://ollama.com). The text
then never leaves this computer, and imports cost nothing. The backend checks a local model's
answers exactly like Claude's, but **expect more points to check**: on the quality check, Qwen3 8B
sometimes chose a wrong category, a quantity without its unit, or kept an introduction as a note
(details in [docs/extraction-quality.md](docs/extraction-quality.md)). It no longer retypes the
recipe, so it cannot misspell its words: see [How the model reads a recipe](#how-the-model-reads-a-recipe).

1. **Install Ollama:** `winget install --id Ollama.Ollama -e`. It runs a small server on this
   computer only (`127.0.0.1:11434`) and starts with Windows; quit it from its tray icon. Do not
   change `OLLAMA_HOST`: that would open it to your network.
2. **Download a model** (about 5 GB): `ollama pull qwen3:8b`. If `ollama` is not found, open a new
   terminal (or use `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`).
3. **Choose it** in `.env`: `RECIPES_EXTRACTOR=ollama`. No restart needed. The import screen now
   says the text stays on this computer, and its button reads "קריאה עם המודל המקומי".

Tested on an RTX 5060 Laptop GPU (8 GB): a long Instagram caption takes 20–30 seconds, a short
recipe 6–20 seconds; the first import after a while also loads the model (a few seconds). Check
with `ollama ps` that the model runs on the GPU: `100% GPU` is fast; a CPU share is much slower.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_EXTRACTOR` | `claude` | `ollama`: read imported text with a local model. |
| `RECIPES_OLLAMA_MODEL` | `qwen3:8b` | The Ollama model to use (`ollama list` shows what you have). |
| `RECIPES_OLLAMA_CONTEXT_TOKENS` | `8192` | The model's working memory for one import. 8k fits qwen3:8b entirely in 8 GB and is enough for long captions (one needed about 4,850). For longer texts the import says it ran out; raise it, and part of the model moves to the CPU. |
| `RECIPES_OLLAMA_TIMEOUT_SECONDS` | `600` | How long one local import may take. |
| `RECIPES_OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama runs. Only addresses on this computer are accepted. |
| `RECIPES_EXTRACTION_MODE` | `references` | How the model answers (below). `text`: it retypes the recipe, the first approach, kept for comparison. Applies to Claude too. |

To free the space again: `ollama rm qwen3:8b`, and uninstall Ollama like any app.

### How the model reads a recipe

A small model retyping Hebrew sometimes swaps a word for a similar-looking one: Qwen3 8B turned
"מג׳הול" into "מג׳ hollow" and "שוט" into "שט". So, by default, the model does not retype the
recipe at all:

1. The backend cuts your text into **numbered passages**: each line, and inside a line each
   sentence, and each item of a list after a label ("מה צריך: כוס עדשים, כוס אורז, …"). The same
   text always gives the same passages.
2. The model sees the text with the numbers (`[4] חצי תמר מג׳הול`) and answers with **a role for
   every passage, in order**: title, ingredient heading, ingredient (also what is only for a
   topping, a garnish or serving), step heading, step, "continues" (the rest of the passage before
   it), tip, yield or time (kept as a note), or not part of the recipe (introductions, calls to
   action, hashtags). The answer's format lists every passage, so none can be skipped.
3. The backend **copies each ingredient, step, heading and tip from your text**, character for
   character, in the text's order. Only bullets, step numbers and emoji at the start of a line are
   left out.
4. The backend **reads each ingredient's quantity from its copied line**, by fixed rules
   ([docs/quantity-conventions.md](docs/quantity-conventions.md)): the amount and its unit, wherever
   they are ("3 כוסות" in "3 כוסות קמח", "אחד" in "בצל אחד גדול"), or nothing when the line has no
   amount. The quantity is always a piece of the line, never a converted or invented amount.

The model still decides a few things, and the backend checks each:
- a **title**: the line that names the dish. A title it says is written must start a line of the
  text; if the model retyped it wrongly but labeled the title line, that line's own words are used;
  a title line that is only a framing label ("ארוחת בוקר של שישי:") keeps the rest of its line;
  an introduction sentence that only mentions the dish is not a title. When no line names the
  dish, the model composes the dish's own name (what it is, its main ingredients) from the text's
  words, the introduction included, without the occasion or hype words (measured results and
  what still slips through: docs/extraction-quality.md). A composed title is always flagged for review, also
  when the model claims it is written, and the point says whether all its words are in the text;
- the **servings**: kept only from a line that says it is the yield ("12 יחידות", "Serves 2");
  otherwise the field stays empty. A passage the model labeled "not part of the recipe" (such as
  an instruction written inside the text) never supplies the servings or the title;
- **whether the text is a recipe at all**: with the local model this is decided in the first
  request, together with the roles, **without your categories in view**. Whether a category fits
  is a separate question: a recipe that fits none is imported normally, unclassified (measured:
  with the categories in the same request, your drink caption was called "not a recipe" in 8 of
  12 tries);
- the **category**: only one of your existing categories, chosen by their descriptions (a
  category's name can be a personal label; its description decides), and when unsure the recipe
  stays unclassified, which never prevents saving it. With the local model the category is asked
  in a second, short request about the finished draft (its copied lines). The starter categories
  are yours: "קינוחים" (sweet desserts, dairy desserts included), "ארוחות בשריות" (meat and poultry
  meals), "ארוחות קלילות" (savory dairy or egg meals; "light" is a personal label, not about
  calories or portions) and "משקאות" (drinks, smoothies, coffee drinks, lemonade). A fish, vegetable
  or legume dish usually fits none and stays unclassified;
- **roles, corrected by the surrounding structure**: a short line in the ingredient list that says
  what it is for ("לציפוי - מלח מאלדון", "להגשה: גלידת וניל", "Lemon wedges, for serving") is an
  ingredient, as written, with no invented quantity, even if the model called it a tip;
- **which passages to point out**: the model can point at a passage that looks cut off or
  unclear, an "or" whose scope is unclear, or a request inside the text, and at an ingredient a
  step uses that the list does not have. The **messages are written by the backend**, quote the
  passage, and appear once. An ingredient a step uses that the list leaves out ("מקשטים בתותים"
  with no strawberries listed) is also found by the backend itself, from a general list of
  ingredient words: the recipe is kept as your source wrote it, nothing is added, no amount is
  guessed, and a review point tells you. Missing information (an oven temperature, a baking time)
  is checked by the backend from the text itself.

Anything the backend cannot place is flagged, never guessed: a passage without a role, or one
that "continues" nothing, becomes a review point that quotes it ("קטע שלא שובץ", "הפניה לא
תקינה"). Your original text is saved unchanged with the recipe.

## Commands

Backend, from `backend/`:

| Command | What it does |
|---|---|
| `uv run pytest` | Backend tests. No network: the API is called in-process, each test gets its own temporary database, and HTTP, Claude and Ollama are replaced by stand-ins. Your `data/` folder, `.env` and API key are never used. |
| `uv run python -m evals.run_extraction` | **Paid with Claude.** The extraction quality check: one real request per case (at most 40). See [Three kinds of checks](#three-kinds-of-checks). |
| `uv run python -m evals.run_extraction --extractor ollama --cases-dir ../data/evals/local-cases` | The same check with the local model: free, about 7 minutes for all 30 cases on an 8 GB GPU. |
| `uv run python -m evals.compare <run folder> <run folder>` | Two quality-check runs side by side, case by case. |
| `uv run python -m evals.rescore <run folder> …` | Scores saved runs again with today's expectations and checks, from their saved drafts. No model calls. |
| `uv run python -m evals.rebuild <label> <run folder> …` | Rebuilds saved runs' drafts from their saved model answers with today's backend code, and scores them: measures a backend change alone. No model calls. |
| `uv run python -m app.migrate` | Upgrades the database now (the backend also does it when it starts), after a backup copy. |
| `uv run alembic history` | Lists the database migrations. |
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
- **Probe runs:** `<data folder>/instagram-probe/<run-id>/`. **Quality check results:**
  `<data folder>/evals/extraction/<run>/`.

**Database upgrades.** When a new version of the notebook needs a changed database (a *migration*,
for example milestone 4's draft status and original texts), the backend upgrades it when it starts.
It first copies the file to `recipes.backup-<date>-<time>-before-<migration>.db` in the same folder,
then upgrades it in one step that either completes or changes nothing. Your recipes are kept. The
terminal says what it did. To go back, stop the backend and put the backup copy in place of
`recipes.db`. Delete old backup copies when you no longer need them.

Settings use the `RECIPES_` prefix. You can set them in a `.env` file: copy `.env.example` to `.env`
in the repository root and edit it in VS Code, which saves UTF-8. `.env` is git-ignored. The backend
reads it when it starts. A real environment variable wins over `.env`.

| Setting | Default | What it does |
|---|---|---|
| `RECIPES_DATA_DIR` | `data/` in the repository | Where the database and other local data are kept. |
| `RECIPES_SQL_ECHO` | `false` | `true` prints every SQL statement the backend runs, in its terminal. Useful for learning what the ORM does. |
| `ANTHROPIC_API_KEY`, `RECIPES_MODEL`, `RECIPES_MODEL_TIMEOUT_SECONDS` | | See [Connect the Claude API](#connect-the-claude-api). |

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
3. **Extraction quality check** (`uv run python -m evals.run_extraction`, from `backend/`): real
   model requests (paid with Claude, free with the local model) on representative recipe texts,
   compared with expectations written by hand (changed wording, missing or invented lines,
   quantities, timings, grouping, classification, missing flags, unnecessary warnings). Run
   explicitly; at most 40 cases per run. Cases: `backend/evals/cases/` (invented
   texts, in git) and, with `--cases-dir ../data/evals/local-cases`, your own (for example real
   captions; git-ignored). The report is saved in `data/evals/extraction/`; findings are recorded in
   [docs/extraction-quality.md](docs/extraction-quality.md). Milestone 7 extends it.

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
│   │   ├── migrate.py               brings the database up to date at start-up (with a backup first)
│   │   ├── crud.py                  reading and writing recipes; the category check
│   │   ├── seed.py                  fills a new database once
│   │   ├── sample_data.py           the starter categories and the four invented sample recipes
│   │   ├── api/                     recipes.py, categories.py, imports.py (pasted text or an Instagram link -> draft)
│   │   ├── extraction/              passages (segments.py), answer schema, prompts, Claude / Ollama calls, the checks
│   │   └── importers/instagram.py   Instagram URL parsing, page capture, caption analysis, reading a post for an import
│   ├── migrations/                  database migrations (Alembic): 0001 milestone 3, 0002 imports, 0003-0005 categories, 0006 Instagram originals
│   ├── alembic.ini                  Alembic's settings, for its command line
│   ├── evals/                       the extraction quality check (paid; run by hand) and its cases
│   ├── scripts/probe_instagram.py   bounded live probe and offline analysis
│   └── tests/                       pytest: API, persistence, migrations, extraction, contract, importer, settings…
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
│       │                            (with IngredientsEditor, StepsEditor, RowButtons, FieldError), CategoryChip,
│       │                            ImportPanel, ReviewIssues, OriginalText
│       ├── test/                    test setup, the fake API, sample recipes as test data
│       └── *.test.ts(x)             Vitest + Testing Library tests
└── data/                            local data (git-ignored)
```
