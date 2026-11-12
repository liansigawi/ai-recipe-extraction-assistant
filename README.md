# AI Recipe Extraction Assistant

I built a personal recipe notebook because the recipes I saved were scattered across Instagram, websites, and notes. The app turns those sources into editable recipe drafts and organizes the recipes I keep in a searchable Hebrew notebook.

**[Browse the live demo](https://recipe-notebook-5fi.pages.dev)** · **[See a source-to-recipe example](https://recipe-notebook-5fi.pages.dev/#/recipes/12/source)** · **[Read the evaluation](docs/extraction-quality.md)**

The public demo is read-only. It shows saved recipes and recorded examples of extraction and review. Importing, running the model, and editing happen in the local app.

## What it does

- **Import recipes** from pasted text, public Instagram posts, and supported recipe websites.
- **Keep the source beside the draft** so you can check ingredient amounts, steps, and flagged details before saving.
- **Suggest a category** from your existing categories. You can change it or leave the recipe unclassified.
- **Find recipes later** by name, ingredient, category, or whether you've cooked them.

## How it works

The key design decision was to **let the model identify what each passage is, then let the backend copy the recipe wording from the source**. Early experiments with direct rewriting sometimes changed Hebrew words. Giving the model numbered passages to label reduced the need to regenerate the recipe.

1. **Read the source.** Get the public Instagram caption, pasted text, or recipe page. Prefer structured recipe data when a website provides it; otherwise use the page's main text.
2. **Build a draft.** For text sources, the model labels passages as ingredients, steps, notes, or unrelated content. The backend assembles the draft from the selected passages and reads quantities using fixed rules. When a site provides structured recipe data, the app can build the draft without model-based text extraction.
3. **Classify and check.** The model suggests a category. The backend checks for issues such as an ingredient mentioned in the instructions but missing from the ingredient list.
4. **Review and save.** Compare the draft with the source, make corrections, and save to SQLite.

In the [vanilla torte example](https://recipe-notebook-5fi.pages.dev/#/recipes/12/source), the system flagged strawberries mentioned only in the instructions. Review added them without inventing a quantity and corrected the model's dessert type.

## What I measured

I compared two prompts for the same local model, **Qwen3:8B**. Asking for the category directly, without first asking the model to describe the dish, improved classification on the same 119-case evaluation set:

| Classification metric | With dish description | Direct classification |
| --- | ---: | ---: |
| Main category correct | 90 / 119 | 98 / 119 |
| Fully correct classification | 74 / 119 | 86 / 119 |

“Fully correct” means the main category and, for desserts, the dessert type. These results measure classification on this collection, not recipe extraction accuracy or expected performance on future imports. See the [evaluation notes](docs/extraction-quality.md) for the method, held-out results, and cases that got worse.

I kept model evaluation separate from offline software tests, which cover the API, persistence, extraction rules, and review interface.

## Tech stack

| Area | Tools |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| Backend and storage | Python, FastAPI, SQLite, SQLAlchemy, Alembic |
| Model | Qwen3:8B via Ollama; optional Claude API integration |
| Testing and public demo | pytest, Vitest, Playwright, Cloudflare Pages |

## Run locally with Ollama

Tested on Windows 11. Install **uv**, **Ollama**, and a compatible **Node.js** version (see [frontend/package.json](frontend/package.json) for supported versions). Start Ollama, then run:

```powershell
git clone https://github.com/liansigawi/ai-recipe-extraction-assistant.git
cd ai-recipe-extraction-assistant
ollama pull qwen3:8b
Copy-Item .env.example .env
```

In the new `.env`, set `RECIPES_EXTRACTOR=ollama`. No API key is needed in this mode.

Open two terminals from the repository root:

**Backend**

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
```

**Frontend**

```powershell
cd frontend
npm ci
npm run dev
```

Open [localhost:5173](http://localhost:5173) and try importing pasted recipe text first. For the optional cloud configuration, see [`.env.example`](.env.example).

The [setup guide](docs/setup.md) covers the full installation (including the Chromium download that Instagram import needs), the Claude API option, settings and backups, and Windows troubleshooting. The [user guide](docs/user-guide.md) explains each screen and what to do when an import fails.

## Limitations and further reading

- The model can misclassify recipes or miss details. Drafts are designed for review before saving.
- Instagram import is limited to public posts the app can read without signing in. Some recipe sites block automated access or only expose the recipe after running scripts. Pasting the text is a fallback.
- Screenshot import is not available in the current app.

[Setup](docs/setup.md) · [User guide](docs/user-guide.md) · [Development](docs/development.md) · [Architecture](docs/architecture.md) · [Quantity rules](docs/quantity-conventions.md) · [Instagram feasibility](docs/instagram-feasibility.md) · [Website import](docs/website-import.md) · [Public export](docs/public-notebook.md) · [Maintenance](docs/maintenance.md)
