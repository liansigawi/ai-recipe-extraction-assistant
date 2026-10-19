# Local Recipe Notebook

A personal recipe notebook that runs on your own computer. It imports recipes from Instagram posts,
recipe websites, screenshots, or pasted text; lets you review them; and keeps them in a searchable
collection that supports Hebrew and right-to-left text.

> **Status: milestone 1 of 7 — the Instagram import feasibility probe.** The app itself (a FastAPI
> backend and a React frontend) starts in milestone 2. The plan is in
> [docs/architecture.md](docs/architecture.md), the findings are in
> [docs/instagram-feasibility.md](docs/instagram-feasibility.md), and the original requirements are
> in [docs/brief.md](docs/brief.md).

## Privacy: what stays on this computer

- Recipes, the SQLite database, and uploaded screenshots are stored in a local data folder
  (`data/` by default, excluded from git).
- **This is not a fully offline app.** From milestone 4, recipe text and images that you submit for
  AI extraction are sent to the Anthropic API.
- The Instagram probe and importer contact Instagram's servers directly from this computer:
  instagram.com, plus its content hosts (cdninstagram.com, fbcdn.net) when a browser is used.

## Requirements

| Tool | Tested version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.13.1 | Manages Python, the virtualenv and the dependencies. |
| Python | 3.14.8 | uv downloads it automatically (about 22 MB). 3.14.7 or newer is required: 3.14.0–3.14.6 have an asyncio bug that makes Playwright hold on to memory. |
| Chromium for Playwright | Playwright 1.64.0, Chromium 156.0.8078.4 | About 330 MB download, about 720 MB on disk (full Chromium plus a headless build). |
| Node.js | 24.18.0 (installed, not used yet) | Needed for the frontend from milestone 2. |

Python packages are pinned in `backend/uv.lock`. Tested together: playwright 1.64.0, pydantic 2.14.1,
httpx 0.28.1, beautifulsoup4 4.15.0, pytest 9.1.1.

## Setup (tested on Windows 11)

1. Install uv:
   - Windows: `winget install --id=astral-sh.uv -e`
   - macOS / Linux (not tested here): `curl -LsSf https://astral.sh/uv/install.sh | sh`

   Then **close and reopen your terminal app**. If you use VS Code's built-in terminal, restart VS
   Code completely; a new terminal tab is not enough. Check it worked with `uv --version`.
2. Install the backend environment. This creates `backend/.venv` with Python 3.14.8 and the exact
   package versions in `backend/uv.lock`:

   ```bash
   cd backend
   uv sync
   ```

3. Download Playwright's Chromium. Do this once per computer, and again whenever the Playwright
   version in `uv.lock` changes. It is stored outside the project, in `$env:LOCALAPPDATA\ms-playwright`
   on Windows:

   ```bash
   uv run playwright install chromium
   ```

`uv run <command>` runs a command inside the project's environment, so you never need to activate
the virtualenv yourself. In VS Code, choose `backend\.venv\Scripts\python.exe` as the interpreter
(Command Palette → *Python: Select Interpreter*) so the editor sees the installed packages.

## Commands

Run these from `backend/`:

| Command | What it does |
|---|---|
| `uv run pytest` | Offline tests. No network: fixtures are hand-written and HTTP calls are mocked. |
| `uv run python -m scripts.probe_instagram` | Live Instagram check: the three sample posts × 4 strategies = at most 12 page loads, 10 s apart. It stops at the first sign of rate limiting or a login wall. It prints the run folder, where it saves raw pages and a `summary.md`. |
| `uv run python -m scripts.probe_instagram <url> …` | The same check for up to 10 of your own public post or Reel URLs. |
| `uv run python -m scripts.probe_instagram --analyze <run-id>` | Re-analyze a saved run offline (no network). Pass the run ID (for example `20261018-135240`) or the run's folder path. |
| `uv run python -m scripts.probe_instagram --help` | All options with their defaults: `--strategies`, `--headed`, `--channel msedge`, `--delay`, `--timeout`, `--out`, `--analyze`. |

Open `summary.md` in VS Code. Windows PowerShell 5.1's `Get-Content` shows the Hebrew as garbage
unless you add `-Encoding UTF8`.

## Where data lives

All local data goes in one folder: `data/` at the repository root by default, which is excluded
from git. Probe runs are saved in `<data folder>/instagram-probe/<run-id>/`. Back up by copying the
folder.

To keep data elsewhere, set `RECIPES_DATA_DIR` to a **full path** before running a command. A
relative path is rejected, because it could put data somewhere git does not ignore. In PowerShell:

```powershell
$env:RECIPES_DATA_DIR = "D:\Backups\recipe-notebook"   # this terminal session only
setx RECIPES_DATA_DIR "D:\Backups\recipe-notebook"      # permanently, for terminals opened afterwards
```

No `.env` file is read yet; `RECIPES_DATA_DIR` is the only setting. An `.env.example` with the API
key settings arrives in milestone 2, when the backend starts reading `.env`.

## Three kinds of checks

The project keeps these separate and reports which one was run:

1. **Software tests** (`uv run pytest`): deterministic and offline. They prove the parsing and the
   decision logic, not that Instagram works today.
2. **Live importer checks** (`scripts/probe_instagram.py`): run by hand against real Instagram pages.
   Results are recorded with dates in [docs/instagram-feasibility.md](docs/instagram-feasibility.md).
3. **Model-quality evaluation** (milestone 7): compares AI extraction against checked expectations.
   Run explicitly; bounded; uses paid API calls.

## Repository layout (so far)

```text
.
├── README.md
├── .gitignore
├── docs/
│   ├── brief.md                     original requirements
│   ├── architecture.md              plan, data model, API, milestones, decisions
│   └── instagram-feasibility.md     milestone 1 findings
├── backend/
│   ├── pyproject.toml, uv.lock, .python-version
│   ├── app/
│   │   ├── config.py                data folder setting
│   │   └── importers/instagram.py   URL parsing, page capture, caption analysis
│   ├── scripts/probe_instagram.py   bounded live probe and offline analysis
│   └── tests/                       offline tests (analysis, mocked HTTP, probe, config, code hygiene)
└── data/                            local data (git-ignored)
```
