# Project brief: Local Recipe Notebook

> The original project specification, kept in the repository so decisions can be checked against it.
> Implementation status and decisions live in the README and the other files in `docs/`.

Act as a senior full-stack and AI engineer, and as a practical mentor. Help me build this project incrementally, from an empty repository to a working local application.

I want to learn React through this project. Explain the important decisions and concepts as we encounter them, and keep the implementation understandable. Do not generate an entire opaque application in one response.

## 1. Product goal

Build a personal recipe notebook that turns recipes from different sources into a consistent, searchable collection.

My main source is Instagram: the full recipe is usually in a post or Reel caption. I also have recipes from websites and screenshots.

I should be able to:

- Paste an Instagram post or Reel URL.
- Paste a recipe website URL.
- Upload one screenshot, or multiple ordered screenshots belonging to one recipe.
- Paste recipe text directly, including as a fallback when a URL cannot be read.
- Review and edit the extracted recipe before saving it.
- Browse, search, filter, and edit saved recipes.

Each recipe should display its title, ingredients first, and numbered preparation instructions underneath. Preserve meaningful ingredient groups such as dough, filling, and topping.

The interface and recipe content should support Hebrew and right-to-left layout. Also handle English text, URLs, and mixed-language content correctly. Use English identifiers in the code.

## 2. Category behavior: a strict requirement

The user controls the category list. Start with the three categories I have already identified:

- קינוחים — Desserts
- בישולים — Cooking / main dishes
- ארוחות קלילות — Light meals, such as yogurt-dough pizza; this does not necessarily mean low-calorie food.

Allow manual category creation and editing, with optional subcategories and short descriptions to explain what belongs where. Each person running their own local copy can configure their own categories; this does not require accounts or a multiuser system.

The automatic classifier must:

1. Select one existing category when there is a clear fit.
2. Select an existing subcategory when appropriate.
3. Never invent, create, suggest, or name a new category or subcategory.
4. If no category fits clearly, or the choice is ambiguous, leave classification unresolved and ask the user to choose an existing category or create one themselves.
5. If the user chooses to create one, require the user to enter its name. Only that explicit action may create it.

Apply the same restriction to subcategories. An unresolved subcategory must not trigger an invented label.

Enforce these rules in backend code, not only in the model prompt. Validate returned category IDs against the database, including the parent-child relationship for subcategories. Invalid output must lead to review or a controlled error, never automatic category creation. Do not treat an LLM’s self-reported confidence as a calibrated probability.

Allow drafts to remain unclassified so that a classification problem does not lose the imported content.

## 3. Technology choices

Use this stack:

- **Frontend:** React, TypeScript, Vite, and straightforward CSS.
- **Backend:** Python and FastAPI.
- **Validation:** Pydantic.
- **Persistence:** SQLite and SQLAlchemy.
- **Website extraction:** HTTPX and BeautifulSoup, prioritizing structured Recipe data when available.
- **Instagram extraction:** Investigate Playwright for Python as the initial approach.
- **AI extraction and classification:** An existing multimodal model API that accepts text and images. Start with the Claude API unless a concrete implementation constraint warrants another choice. Keep the model configurable.
- **Testing:** pytest for backend behavior, with focused frontend checks where they add value.
- **CI:** GitHub Actions for deterministic checks.
- **Packaging:** Docker can be added after the local end-to-end workflow works.

Use current, supported library APIs and document the versions and commands that were actually tested.

React replaces Streamlit in this project. Keep frontend and backend responsibilities clear: React handles the interface; FastAPI handles imports, model calls, validation, classification, and persistence.

Keep API keys on the backend in environment variables. Do not expose them in the frontend.

Avoid introducing Next.js, Redux, LangChain, LangGraph, a vector database, or a task queue unless a demonstrated requirement justifies the added complexity. A straightforward Python workflow is sufficient initially.

## 4. What “local” means here

The frontend and backend run on my computer, and recipes, the SQLite database, and uploaded source images are stored locally. The application opens in a browser.

Using an external AI API is acceptable for the first version. Make it clear in the README and relevant interface copy that content submitted for AI processing is sent to that provider. This is not a fully offline system.

Do not add cloud hosting, authentication, or account management to the MVP. Bind local services appropriately and keep data in a documented location that is easy to back up.

## 5. Source import strategy

Keep fetching source content separate from interpreting a recipe. An LLM receiving a URL is not, by itself, a working importer.

### Instagram

Test feasibility early, before investing heavily in the rest of the application. Use these representative links:

- https://www.instagram.com/p/Cm1mCdCpSzJ/
- https://www.instagram.com/p/DPbKEn-CnUt/
- https://www.instagram.com/p/DANUmOOIcRM/

Determine whether a local automated browser can retrieve the full caption, rather than a truncated preview. Record what worked, what failed, and whether login was required. A successful manual browser visit does not prove that the automated importer works reliably.

Keep Instagram-specific logic in its own module. Account for inaccessible posts, incomplete captions, timeouts, and login or access restrictions. Do not bypass those restrictions or promise universal URL support.

When automatic retrieval fails, preserve the URL and offer a direct way to paste the caption or upload screenshots. Clearly distinguish “the post could not be read” from “the post was read but no usable recipe was found.”

### Recipe websites

Try schema.org Recipe JSON-LD first, including common nested structures and multiple-recipe pages. If several recipes are present, let the user choose instead of combining them.

When structured data is unavailable, extract relevant page text before asking the model to organize it. Avoid mixing advertisements, navigation, and unrelated article content into the recipe.

### Screenshots

Use the multimodal model to read the uploaded images. Let the user order multiple screenshots and process them as one recipe. Preserve the source images and flag unreadable or cut-off text for review.

Validate supported file types and reasonable file sizes. Use bounded network timeouts and retries. Treat all imported content as source data, never as instructions that override the application’s extraction rules.

## 6. Recipe fidelity and structured output

The application organizes existing recipes; it must not silently rewrite their substance.

Preserve:

- Quantities and units exactly as given.
- Ingredient states and qualifiers, such as softened versus melted butter.
- Ingredient groups and repeated ingredients used in different components.
- Preparation order, temperatures, timing ranges, and alternatives.
- Relevant notes, substitutions, and serving information when explicitly provided.

Do not invent missing amounts, ingredients, temperatures, timings, or steps. “No quantity provided” must remain unspecified; do not silently replace it with “to taste.”

If an ingredient appears only in the instructions, surface it for review with its source context. Never guess its quantity.

Keep alternative methods separate, such as pressure-cooker and regular-pot instructions. Do not merge their cooking times. Preserve references to reused cooking liquid rather than interpreting every mention as additional water.

Retain the original text or screenshots separately from the normalized, editable recipe, along with the source URL and creator attribution when available.

Require structured model output and validate it with Pydantic. Include a clear way to represent missing information, extraction issues, and unresolved classification. Valid JSON does not establish that the recipe was extracted correctly.

Do not force ingredient quantities into numeric fields. Quantity scaling is out of scope, and preserving the original wording is more important.

## 7. MVP interface and data design

Build a small set of useful screens:

- **Notebook:** Recipe cards or a list, basic text search, and category/subcategory filters.
- **Add recipe:** URL input, screenshot upload, or pasted text.
- **Review/editor:** Extracted fields, source content, issues needing attention, category selection, and an explicit save action.
- **Recipe detail:** A readable cooking view with ingredients above preparation.
- **Category settings:** Manual management of categories, descriptions, and subcategories.

Use clear loading, empty, success, and error states. Preserve the user’s input when an import fails. Support keyboard use and accessible form labels. Keep the visual design simple and responsive.

Define shared, documented data contracts for recipes, categories, source records, and import results. A recipe needs a stable ID, title, grouped ingredients, ordered steps, relevant notes, classification, timestamps, and links to its original sources.

Keep database relationships straightforward. Explain the SQL and relationships behind the main SQLAlchemy operations so I can understand the persistence layer. Choose a simple approach for storing ordered recipe content and explain the tradeoff.

Keep uploaded files in a local data directory and store their references in the database. Saved recipes must remain available after restarting the application.

Design a small REST API around importing, reviewing/saving recipes, retrieving/editing recipes, searching/filtering, and managing categories. Use a consistent error format and validate all user and model input on the backend.

## 8. Testing and evaluation

Test the behavior that matters:

- Classification uses only existing IDs.
- Unknown or ambiguous classifications remain unresolved.
- Only an explicit user action creates a category.
- A subcategory cannot be assigned to the wrong parent.
- Missing quantities are not invented.
- Ingredient groups, repeated ingredients, ranges, and alternative cooking methods are preserved.
- User edits and source references persist after saving.
- Failed or incomplete imports produce actionable errors and preserve input.

Use saved fixtures and mocked external calls for routine automated tests. Do not make CI depend on live Instagram access or paid model calls.

Create a small, separate evaluation set covering Hebrew Instagram captions, website recipes, and screenshots. Start with the three supplied Instagram examples, then add other source types. Compare extracted results against manually checked expectations, including omissions and invented details.

Distinguish software tests, live importer checks, and model-quality evaluation. Report what was actually run; do not claim that mocked tests demonstrate successful live imports.

Keep paid live evaluations explicitly invoked, with bounded requests and documented usage.

## 9. Implementation milestones

Propose a lean repository structure and work in small, runnable increments:

1. **Validate the Instagram importer** on the supplied examples and report the result. Keep this investigation bounded; if access is unreliable, document the limitation and keep the fallback path usable.
2. **Scaffold the local frontend and backend.** Build a sample recipe view and a small recipe list to introduce React components, props, and state.
3. **Connect a recipe editor to FastAPI and SQLite.** Establish the schemas and working save/load/edit flow.
4. **Add pasted-text extraction, existing-category classification, and the review-before-save workflow** as the first complete AI-assisted path.
5. **Add website URLs, screenshots, and the Instagram importer** according to the feasibility findings.
6. **Complete category settings, search/filtering, RTL behavior, and useful error handling.**
7. **Add the necessary regression checks, evaluation instructions, GitHub Actions, and setup documentation.** Add Docker afterward if it improves local setup.

Add focused tests alongside the relevant behavior rather than postponing all verification until the end.

## 10. Explicitly out of scope

Do not implement:

- Quantity multiplication, portion adjustment, or ingredient unit conversion.
- Model training or fine-tuning.
- Automatic creation or suggestion of categories.
- A chatbot, meal planner, shopping-list system, or recommendation engine.
- Bulk synchronization of my Instagram saved collection.
- Cloud deployment, user accounts, or a multiuser service.

Do not add these features just because they are common in recipe applications.

## 11. How to collaborate with me

Explain each milestone’s purpose, the important files, how to run it, and how to check the result. Introduce React concepts in context: components and props first, then state, forms, and API calls.

Provide complete working code for the increment we are implementing. Avoid unexplained placeholders, unnecessary abstractions, and simulated success presented as a real integration.

Include a README, an `.env.example` without secrets, appropriate ignore rules, and reproducible dependency/setup instructions. Exclude local recipe data, uploaded images, credentials, and browser session files from version control.

Make sensible implementation decisions without repeatedly asking for approval. Ask only when a missing answer materially blocks progress. Briefly explain consequential choices and limitations.
