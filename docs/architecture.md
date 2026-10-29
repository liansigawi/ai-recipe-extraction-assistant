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
   ├─ extraction/      A model reads pasted text → answer in a fixed JSON schema → checked → draft
   │                   with review issues (milestone 4). Classification is part of the same answer:
   │                   only ids of existing categories; the backend checks them. Never creates categories.
   │                   The model is the Claude API or a local model through Ollama (RECIPES_EXTRACTOR).
   ├─ importers/       FETCH source content only: instagram (milestone 1, used by the app since
   │                   milestone 5); website, screenshots (planned, milestone 5). No AI.
   └─ media            Pictures and videos under data/media/ (one file per content, shared, removed
                       when unused); which belong to which recipe in the database (milestone 6).
          │
          ├─► Anthropic API (external, from milestone 4): only the pasted text and the category list.
          └─► or Ollama on 127.0.0.1:11434 (this computer): the same request, nothing leaves the machine.
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
  "category": { "id": 2, "name": "ארוחות בשריות" },
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
  (collaboration posts have two): `{ "name": "ריטה קדוש", "username": "ritakadosh_" }`, a display name,
  an Instagram username (without "@"), or both. This is the editable credit; an Instagram import fills
  it from the post's own data. `original.author` and `original.coauthors` keep who posted it as read,
  and never change. A credit sent as one string (older clients) is still read: "@user", or a bare
  username on an Instagram source, is a username, anything else a name.
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
  2. segments.py cuts the text into numbered passages; prompt.py builds the request.
     claude.py (or ollama.py): one request, with structured output (the JSON schema of
     extraction/output.py: one required role per passage, category ids limited to the existing
     ones), a 16,000-token answer limit, a timeout (Claude: 120 s a request; locally: 300 s of
     clock time for the whole import, both requests together, time asleep included; the answer is
     streamed and the clock checked at every piece, and when the time is up the connection closes,
     Ollama stops generating and nothing is saved) and, for Claude, two automatic retries for
     temporary errors. The local model's first request has no categories in it (roles and "is
     this a recipe" only); a second, short request then asks the category of the finished draft
     (one retry on a server error; if it fails, the draft is unclassified, unless the import's
     time is up: then nothing is saved).
  3. review.py: copies each labeled passage from the original, checks every other part of the
     answer and builds a draft with issues (below).
  4. crud.create_import: checks the category ids against the database again, then saves the
     draft (status "draft") and the original text in one transaction.          → 201 + the draft
Any failure before step 4 saves nothing; the page keeps the pasted text (also in localStorage).
```

**The pasted text is data, not instructions.** It goes into the user message between tags whose
name ends with a random suffix made for each request, so the text cannot close the tag and pose
as instructions; the system prompt says to ignore requests inside it. The answer can only be the
schema's fields, and is checked like any other answer. Evaluation case 08 tests exactly this.

**The checks in `review.py`** (nothing the model says is taken on trust):
- in reference mode (the default), ingredient lines, steps, notes and group names are not written
  by the model at all: each is the exact text of the passages it labeled. Every passage must have
  a role; one without, or a "continues" with nothing before it, becomes an `unused_text` or
  `invalid_reference` issue that quotes it. Labels ("איך מכינים:"), lines of only hashtags and the
  title line are never content, whatever role they get;
- in text mode, every title, ingredient line, step, note and group name must appear in the original text (after
  normalizing only spacing, Unicode form and invisible marks); a line that does not is kept, with a
  `not_found_in_source` issue that quotes it;
- in reference mode the quantity is not the model's: `quantity.py` reads it from the copied line
  by the rules of [quantity-conventions.md](quantity-conventions.md), as a span of that line. In
  text mode every quantity must be written in its own line (`quoted_from`, the contract's rule);
  otherwise it becomes `null` with a `quantity_not_in_line` issue, never an invented amount;
- a title the model composed (no title in the text), or one it says is written but no line starts
  with, gets a `missing_title` issue;
- classification: only `fit = "clear"` with an existing category id (and, if given, one of that
  category's subcategories) classifies. Anything else, including an inconsistent answer, stays
  unclassified with a `classification_unresolved` issue whose message is written by the backend,
  from the database's own category names;
- review points are tied to evidence, with fixed messages written here. In reference mode the
  model writes no messages: it points at a passage and names the kind (`unclear_text`,
  `ambiguous_alternative`, `multiple_recipes`, or a request inside the text, shown as `other`),
  and the passage is quoted; a point without its passage is not shown. "Used in the steps but not
  listed" (a source that leaves an ingredient out of its list) is found by the backend itself, from
  a general list of ingredient words (`ingredient_words.py`), and from the model's claims, each
  shown only if the step writes those words and no ingredient line has them; nothing is added to
  the list and no amount is guessed. Missing information (an oven temperature, a baking time) is
  decided here, from the text. A tip labeled inside the ingredient list gets a point: it may be an
  ingredient. The same point is never shown twice;
- the surrounding structure corrects a label: a short line inside the ingredient list that says
  what it is for ("לציפוי - מלח מאלדון", "קרח להגשה", "Lemon wedges, for serving"), or a line
  under a "להגשה:" heading, is an ingredient, as written, even when the model labeled it a tip. A
  time label and its value on one line, or a tip cut at a comma, are one note;
- servings are kept only from a passage that says it is the yield ("12 יחידות", "Serves 2"), and
  a passage labeled "not part of the recipe" never supplies the servings or the title;
- in text mode, issue messages from the model that mention categories are dropped, so no text in
  the draft can suggest a new category; quotes that are not in the original are removed; the
  model's own issues are kept, at most 20.

**Review and explicit save.** The draft opens in the editor with the original text (sticky, so it
stays in view) and the issues; each issue can be marked "handled". "Save as recipe" (a plain
button, never the form's Enter key) sends `status: "saved"` and no issues; "save draft" (the form's
default action) keeps `status: "draft"` and the open issues. A draft may stay unclassified.

**Without the model.** `use_model: false` saves the text as a draft without calling Claude, with a
`not_extracted` issue and the first line as a stand-in title, for the person to fill in. It works
with no API key.

## Import flow (milestone 5: an Instagram link)

```text
ImportPanel ── POST /api/imports/instagram {url, use_model} ──► app/api/imports.py
  1. parse_instagram_url: /p/, /reel/, /reels/, /tv/, with a username first, with ?igsh=...; the
     canonical address. Anything else (another site, stories, share links): 422 invalid_instagram_url.
  2. retrieve_caption (importers/instagram.py), run in its own event loop (a Proactor loop on
     Windows: the server's own loop cannot start the browser), at most two bounded page loads:
       a. the post page in a fresh logged-out Chromium; analyze_capture reads the post's own data
          (the complete caption, its author and co-authors);
       b. only if that gave no complete caption and Instagram did not say "unavailable", "no
          caption" or "wait": the public embed view over plain HTTP, once;
       c. neither complete: a preview from either page -> caption_incomplete; nothing: the reason.
  3. Read: the caption goes through step 2 onward of the pasted-text flow above (the same
     extraction, quantities, separate classification and checks).
  4. create_import: the draft with kind "instagram", the caption exactly as read, the canonical
     address and which page supplied it (recipe_imports); the recipe's source is the post with
     its creators (editable).
  5. media.attach_post_media: the post's pictures and videos (from the same page load: the
     post's data lists them, in order, with a poster for each video) downloaded from Instagram's
     media servers and attached to the draft. Bounded: 20 MB a picture, 150 MB a video (else
     a smaller version, else its poster only), 400 MB a post, 30 s a request, 180 s the post, 20
     items. Any failure here leaves the draft saved, with a media_incomplete review point that
     says what was saved.
```

Failures save nothing, and their `details` carry the address, the caption if one was read, and the
page loads (`attempts`), so the page can offer pasting the caption with the link kept:

| Code | HTTP | When |
|---|---|---|
| `invalid_instagram_url` | 422 | not a link to one post or Reel |
| `duplicate_link` | 409 | a draft or a recipe already links to the same post (its original or its sources; compared by shortcode); `details.matches` lists them; sent again with `allow_duplicate: true` it imports another copy. Checked before anything is fetched |
| `instagram_unavailable` / `instagram_login_required` | 502 | Instagram says so (deleted, private, gated) |
| `instagram_rate_limited` | 429 | Instagram asks to wait (no second page is tried) |
| `instagram_no_caption` | 422 | the post has no caption |
| `instagram_caption_not_found` / `instagram_error` | 502 | the page loaded but showed no caption / could not be loaded |
| `instagram_timeout` | 504 | no answer in time |
| `instagram_caption_incomplete` | 409 | only a preview, which may be cut off: the page puts it in the text box |
| extraction errors (`not_a_recipe`, ...) | as for text | the caption was read: it comes back in `details` |

**The pasted fallback.** `POST /api/imports/text` takes an optional `url` (an Instagram address,
normalized the same way): the original is `kind: "text"` with that address, and the recipe's source is
the post. With `possibly_incomplete: true` (a preview sent unchanged) the draft starts with a
`caption_incomplete` point.

## Import flow (a recipe website)

```text
POST /api/imports/link {url, use_model, allow_duplicate}
  the host name decides: instagram.com -> import_instagram (above, unchanged); anything else ->
  1. website.check_url: http/https, a host name, ports 80/443, no user:password, never localhost,
     .local/.internal names or a private/loopback/link-local/shared address (literal or resolved).
  2. duplicate check by website.page_key (host without www, path without the final "/", query
     without tracking parameters), before anything is fetched; again with the page's own address.
  3. WebReader.page: one GET, no redirects followed blindly (each hop re-checked, at most 5), the
     address actually connected to checked before anything is read, 3 MB, 30 s, HTML only, an
     honest User-Agent, no cookies, no scripts run.
  4. website.analyze: Schema.org Recipe from JSON-LD (any shape: @graph, lists, HowToSection,
     HowToStep, strings with numbering) or microdata; one recipe, or the one the page's heading names,
     else "ambiguous" (never merged). A bot-check page is "blocked".
  5a. recipe data -> structured_draft: its words as they are (HTML and list numbering removed),
      quantities by quantity.py, review points that need no model (ingredients only in the steps,
      baking information); the model's classify_draft only chooses an existing category.
  5b. no recipe data -> website.main_text (comments, navigation, ads, related posts removed, but
      never the main content's own element or the layout wrappers around it, whatever their names,
      nor a block inside it that holds most of its text, such as a "print" area around the recipe;
      the recipe card or the article first) -> the same extraction as pasted text; a draft with no
      ingredient lines or no steps is refused as incomplete (nothing half-filled is saved).
  6. create_import: kind "website", the page's address, retrieved_from json_ld / microdata /
     page_text, the text read (or the recipe data rendered as text), and source_details: author,
     site name, picture address, the raw recipe data. The source is the page, with its author.
  7. the main picture: WebReader.image (the same checks, 20 MB) -> media.attach_website_image
     (origin "website"); a failure is a media_incomplete review point, never a failed import.
```

**The pasted fallback** takes a website's address too: `POST /api/imports/text` with `url` keeps it as
the original's address and the recipe's `website` source.

**Not yet:** screenshots will fetch nothing and send the images to the model.

## Data model (milestones 3 and 4)

The database is one SQLite file, `<data folder>/recipes.db`. The tables are defined as SQLAlchemy
classes in [`backend/app/models.py`](../backend/app/models.py), and created and changed by
migrations (below). A new database also gets the four starter categories and the four sample
recipes (`backend/app/seed.py`), once: deleted samples are not added again.

| Table | Columns | Notes |
|---|---|---|
| `categories` | `id`, `name`, `description`, `parent_id` (NULL = top level) | Subcategories are rows whose parent is a top-level category (one level deep). `UNIQUE(id, parent_id)` lets recipes reference the pair. The four starter categories (קינוחים, ארוחות בשריות, ארוחות קלילות, משקאות) and the two dessert subcategories (קינוחים רגילים, קינוחים בריאים) are created with the database; after that only the user manages categories (milestone 6). |
| `recipes` | `id`, `title`, `category_id`, `subcategory_id`, `servings`, `ingredient_groups` (JSON), `step_groups` (JSON), `notes` (JSON), `is_sample`, `created_at`, `updated_at`, `status`, `issues` (JSON), `cooked` | Composite foreign key `(subcategory_id, category_id) → categories(id, parent_id)`, so the database rejects a subcategory under the wrong parent. See the enforcement notes below. Times are stored as UTC. `status` is `'draft'` or `'saved'` (a CHECK constraint). `cooked` (0 until you mark it, migration 0010) is separate from both and changed only by its own endpoint. |
| `recipe_sources` | `id`, `recipe_id`, `position`, `kind`, `url`, `creators` (JSON) | Editable attribution, in order. Deleting a recipe deletes its sources; saving replaces them. |
| `recipe_imports` | `id`, `recipe_id` (unique), `kind`, `original_text`, `model`, `imported_at`, `url`, `retrieved_from`, `source_details` (JSON) | The imported original, exactly as pasted or read. `kind` is `text` (pasted), `instagram` (the caption, read from the post) or `website`; `url` is the post's or page's address (also for text pasted after a failed read); `retrieved_from` is `post_page` or `embed_view` for a caption, `json_ld`, `microdata` or `page_text` for a page. `source_details`: who posted it as read (and for a page its site name, picture address and raw recipe data). `model` for a page's recipe data is the model that chose only its category. Written once, when the import is saved; saving the recipe never touches it; deleting the recipe deletes it. |

| `media_files` | `id`, `sha256` (unique), `path`, `content_type`, `size_bytes`, `created_at` | A picture or video under `<data folder>/media/`, at `<2 hex>/<sha256>.<ext>`: the same bytes are one file. Its type comes from its first bytes. Deleted (row and file) only when no attachment uses it. |
| `recipe_media` | `id`, `recipe_id`, `kind` (image/video), `status` (saved/thumbnail_only), `file_id`, `thumbnail_file_id`, `origin` (instagram/upload/website, migration 0011), `post_url`, `post_shortcode`, `post_index`, `width`, `height`, `is_cover`, `created_at` | A recipe's picture or video: the post's items in the post's order, then uploads and a recipe page's main picture (`post_url` is the page). `UNIQUE(recipe_id, post_shortcode, post_index)`: fetching again adds nothing twice. At most one cover per recipe (a partial unique index). A video that could not be saved keeps its poster (`thumbnail_only`). Deleted with its recipe. |

Planned: screenshots for extraction (the next milestone) will add their own table.

**Migrations.** Schema changes are Alembic scripts in `backend/migrations/versions/`: `0001`
creates the milestone-3 tables statement for statement (a test compares it with
`tests/fixtures/milestone3_schema.sql`); `0002` adds `status`, `issues` and `recipe_imports`
with `ALTER TABLE ... ADD COLUMN`, which keeps the existing rows in place; `0003` replaces the
three starter categories' descriptions, only where a description is still the starter text; `0004` and
`0005` do the same for the user's own meanings, and `0005` also renames "בישולים" to "ארוחות בשריות" in
place (same id, so its recipes stay in it) and adds "משקאות" to a notebook that already has categories
(a new one gets it from the seed); `0006` adds the Instagram address to the originals; `0007` adds the
two dessert subcategories under the top-level "קינוחים" (ids after the top-level ones, as the seed
gives them), changing no recipe; `0008` rewrites each credit as `{name, username}` and adds
`recipe_imports.source_details` (who posted it, as read). At start-up,
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
| `PUT /api/recipes/{id}/cooked` | `{cooked: true \| false}` → the recipe; nothing else changes (not even `updated_at`); saving a recipe never sets it | ✅ milestone 6 |
| `DELETE /api/recipes/{id}` | Delete with its sources (204, no body) | ✅ milestone 3 |
| `GET /api/categories` | Top-level categories with their subcategories, for the picker | ✅ milestone 3 |
| `POST /api/categories` | A new top-level category, or with `parent_id` a subcategory of a top-level one (201); `category_name_taken` (409) when its siblings have the name, `invalid_parent` (422) | ✅ milestone 6 |
| `PUT /api/categories/{id}` | A new name and description; the id, the parent and every recipe stay (200); `category_not_found` (404) | ✅ milestone 6 |
| `DELETE /api/categories/{id}` | Removing a category (what happens to its recipes needs a decision) | planned |
| `GET /api/extraction` | Is an API key configured, and which model imports use (never the key) | ✅ milestone 4 |
| `POST /api/imports/text` | Pasted text → a saved draft with review issues and the original (201) | ✅ milestone 4 |
| `POST /api/imports/instagram` | An Instagram post's address → its caption, read from the post → the same draft flow (201); failures above | ✅ milestone 5 |
| `GET /api/media/{file_id}` | A saved picture or video, with its type; byte ranges for seeking | ✅ milestone 6 |
| `POST /api/recipes/{id}/media` | Upload a picture (the body is the file; JPEG, PNG, WebP or GIF, up to 20 MB) → the recipe (201); `unsupported_media` (415), `media_too_large` (413) | ✅ milestone 6 |
| `POST /api/recipes/{id}/media/instagram` | Fetch the media of the recipe's own Instagram post (or `{url}`) → `{recipe, report}`; nothing else about the recipe changes, nothing is added twice | ✅ milestone 6 |
| `PUT /api/recipes/{id}/cover` | `{media_id}` or `{media_id: null}` (the first picture) → the recipe | ✅ milestone 6 |
| `DELETE /api/recipes/{id}/media/{media_id}` | Remove an attachment → the recipe; its file stays while another recipe uses it | ✅ milestone 6 |
| `POST /api/imports/link` | Any recipe link: an Instagram post → the Instagram import; any other page → the website import (above) (201). `website_<reason>` errors with `details.url`: `invalid_url`, `forbidden_address` (422); `blocked`, `not_found`, `http_error`, `unreachable` (502); `timeout` (504); `not_html`, `too_large`, `no_recipe`, `incomplete`, `ambiguous` (with `details.recipes`) (422); `duplicate_link` (409) | ✅ first version |
| `POST /api/imports/screenshots` | Ordered images → the same draft flow | planned |
| `GET /api/files/{id}` | Serve a stored source image | planned (milestone 5) |

Error codes the page branches on: `recipe_not_found` (404), `invalid_request` (422, with the invalid
fields in `details`), `unknown_category` and `subcategory_not_in_category` (422, with the field in
`details`), and `forbidden_origin` (403). Imports add `not_a_recipe` (422),
`extraction_not_configured` and `extraction_busy` (503), `extraction_timeout` (504), and
`extraction_auth_failed`, `extraction_unreachable`, `extraction_refused`, `extraction_incomplete`,
`extraction_invalid_output`, `extraction_failed` (502). A local `extraction_timeout` carries the limit
in `details.seconds`. The same import request sent again while it is still running (after a reload,
from a second tab) shares that run (`app/api/shared_runs.py`): one generation, one draft, the same
answer for both.

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
│   │   ├── media.py          pictures and videos: bounded downloads, uploads, content-addressed files, cleanup
│   │   ├── seed.py           fills a new database once
│   │   ├── sample_data.py    the starter categories and the four invented sample recipes
│   │   ├── api/              recipes.py, categories.py, imports.py, media.py: the routes
│   │   ├── extraction/       output.py (answer schema), prompt.py, claude.py / ollama.py (the model call),
│   │   │                     choose.py (which one), segments.py (numbered passages), review.py (checks),
│   │   │                     quantity.py (quantities), ingredient_words.py (ingredients only in the steps)
│   │   └── importers/        instagram.py (milestone 1); website.py, screenshots.py (milestone 5)
│   ├── migrations/           Alembic: env.py, versions/0001_milestone_3.py … 0010_cooked.py
│   ├── scripts/              probe_instagram.py: live checks, run by hand
│   ├── tests/                pytest: offline, fixtures and in-process API calls only; never calls Claude
│   └── evals/                the extraction quality check, run by hand; cases/ (invented texts), compare.py
├── frontend/                 React + TypeScript + Vite
│   └── src/                  main.tsx, App.tsx, route.ts, types.ts, api.ts, editorForm.ts, recipeFilters.ts,
│                             importLinks.ts, categoryLook.ts, credit.ts, media.ts, components/, test/
├── data/                     git-ignored: recipes.db, media/, instagram-probe/
└── .github/workflows/        (milestone 7) CI: deterministic checks only
```

## Milestones

| # | Milestone | Main concepts |
|---|---|---|
| 1 | ✅ Instagram feasibility probe ([findings](instagram-feasibility.md)) | Separating fetching from interpretation; capturing raw data so analysis is testable offline |
| 2 | ✅ FastAPI + Vite/React scaffold; recipe contract; sample recipe list and cooking view | React: components, props, lists and keys, `useState`, lifting state up, derived values, a first `useRef`/`useEffect`; RTL basics; API error format |
| 3 | ✅ SQLite + SQLAlchemy models, recipe CRUD, editor; the page loads recipes from the API | Controlled forms, `useEffect` + `fetch` with cleanup, loading and error states, `key` to reset state, focus management; SQL behind the ORM, transactions, constraints |
| 4 | ✅ Pasted text → Claude extraction → strict classification → review → save; migrations | Structured output, validating a model's answer, prompt injection, enforcing the category rule in code; migrations and transactions; `localStorage`; work that finishes after the user moved on |
| 5 | Instagram importer ✅; website (JSON-LD first), screenshots (ordered, multimodal) | Fallback paths, file uploads, bounded timeouts; running a browser from a server |
| 6 | Category settings ✅, search and filters ✅, duplicate links ✅, creator credit ✅, pictures and videos ✅, photo gallery and "already cooked" ✅; RTL polish, error handling | Composing screens, accessibility, mixed-direction text; files on disk, `<dialog>`, `<video>` |
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
| 2026-10-20 | A local extractor through Ollama, chosen with `RECIPES_EXTRACTOR=ollama`; same schema, same checks | The user asked to run extraction on their GPU. One small class beside `claude.py`; everything after the model call is shared, so a weaker model produces more review points, never unchecked drafts. |
| 2026-10-20 | Ollama gets the JSON schema twice: as `format` (constrained output) and written into the instructions | Ollama keeps the answer in the schema's shape but, unlike the Claude API, does not show the model the field descriptions. |
| 2026-10-20 | Ollama context 8,192 tokens by default; `think: false` for reasoning models; temperature 0 | Measured on the user's RTX 5060 Laptop (8 GB): 8k keeps qwen3:8b 100% on the GPU (6.2 GB), 10k and 12k spill 11–15% to the CPU; the longest real caption needs about 4,850 tokens. Ollama's default (4k under 24 GB) would cut long captions. |
| 2026-10-20 | The Ollama address must be on this computer | The import screen promises that a local model's text stays here. |
| 2026-10-20 | `review.py` removes decoration (bullets, emoji bullets, list numbers, heading markers), rejoins unnamed list fragments, drops duplicate notes and flags hashtags or "save the post" lines | The local model's quality check run showed these leftovers; all are decoration under the contract's rules, so removing them is safe for every model. Wording is never changed, and promotional lines are flagged, not deleted. |
| 2026-10-20 | **Extraction by reference** (`RECIPES_EXTRACTION_MODE=references`, the default): the model labels numbered passages, and `review.py` copies the recipe's wording from the original. Retyping (`text`) is kept as an option for comparison | The corrupted words were the model's own most likely tokens ("מג׳הול" → " hollow" at 29%, the right "הול" at 8%), identical across 12 runs and with or without the schema: no setting or prompt reliably stops a model from retyping a word wrongly. The backend changed nothing. With references, altered wording fell from 15–21 lines per run to none, and drafts needing no correction rose from 7–8 to 10 of 20; quantities got worse (5 → 11) and imports about 1.9× slower ([extraction-quality.md](extraction-quality.md)). |
| 2026-10-20 | Passages are lines, cut after sentence ends and after a label's colon, and at the commas of a list that follows a label; never at other commas or dashes | The simplest cut that handles the cases: prose paragraphs, "מה צריך: a, b, c" lists, a step that continues on the next line. Cutting at every comma made the model split one ingredient ("1 can chickpeas, drained") or step in two. |
| 2026-10-20 | The answer gives **one role per passage**, under a key the schema writes for the model (number + opening words), all required and in order; not ranges of passage numbers | Tried ranges first: the model forgot the last passages of 4–5 recipes per run (flagged, but missing from the draft) and wrote quantities without their unit, having no line in view. With forced keys no passage can be skipped, and each label and quantity is written next to the passage's own words. Cost: the answer is about 1.5× longer, and an import about 1.9× slower. |
| 2026-10-20 | A title the model wrote that is not in the text is replaced by the passage it labeled as the title | The model retyped "מרק" with a Cyrillic letter in titles too. Its own label says which words are the title, so nothing is guessed; a composed title (none in the text) is still flagged. |
| 2026-10-20 | (Replaced on 2026-10-21.) The quantity was chosen by the model among the line's first words | Exact, but the model's judgment: re-scored on every line, 26 of 143 quantities were wrong, and the amount is not always at the start ("בצל אחד גדול"). |
| 2026-10-21 | **The quantity is read from the copied line by `quantity.py`**, following written conventions ([quantity-conventions.md](quantity-conventions.md)); the model only labels passages | The conventions were written first, then the expectations of all 25 cases by hand (a second, independent annotation agreed on all 144 quantities both covered), then the code. It agreed with every expected quantity, including the 57 of the five held-out cases written by someone else. The quantity is an exact span of the line, so scaling can later change only that span. |
| 2026-10-21 | The evaluation checks every ingredient line and quantity, every preparation sentence, tips, facts (yield, times), text that is not part of the recipe, title, category and expected review points, and counts problems apart from failed checks | The earlier check covered 90 of 143 quantities and could not see a lost "Ready in 10 minutes"; "no correction needed" claimed more than it checked. Re-scored, the baseline had 26 wrong quantities, not 11. |
| 2026-10-21 | Roles: an ingredient includes what is only for topping, garnish or serving; a new `info` role keeps yield and time lines as notes, with their label | Two ingredients ("…להגשה", "לציפוי - …") were kept as notes and "Ready in 10 minutes" was lost. |
| 2026-10-21 | The labels decide whether a text is a recipe | The model once wrote `is_recipe: false` first, then labeled five ingredients and a step: the caption was rejected. |
| 2026-10-21 | Review points: the model points, the backend writes fixed messages and checks the evidence; missing information is decided from the text | The model's own messages were sometimes nonsense ("אין מידע על טמפרטורה של הכביסה…", shown twice, on a recipe that gives its times) and missed real ones (strawberries only in the steps). |
| 2026-10-21 | The local model is asked for the category in a second, short request about the finished draft; if it fails, the first answer's category stays. Ollama server errors on a chat request are retried once | Measured on the same 25 drafts: 2 wrong categories instead of 6 (more left unresolved, which the person settles). About 1 s more per import. The retry: Ollama's GPU runner crashed twice in about 350 requests and worked again on the next one. |
| 2026-10-21 | No example in the instructions or the answer schema may appear in an evaluation case (a test enforces it) | Several examples had come from the cases themselves, including the user's caption, which flatters the measurement. |
| 2026-10-25 | The surrounding structure corrects a label: inside the ingredient list (after an ingredient, before any step), a short line that says what it is for ("לציפוי - …", "… להגשה", "For the topping - …", "להגשה: גלידת וניל") is an ingredient, as written; lines under a "להגשה:" heading too | The model labeled such a line a tip when it ended the list right before the preparation heading (measured: the same line in the middle of the list, or without its purpose word, was an ingredient). A warning to move it by hand was not the fix the user wanted. A sentence, or such a line after the steps, stays a note. |
| 2026-10-25 | Servings only from a passage that says it is the yield; a passage labeled "not part of the recipe" never supplies the servings or the title | Appearing in the text was not evidence: "100 גרם" came from an instruction inside the text, "20×20" from a pan size, "4 טורטיות" from an ingredient line. |
| 2026-10-25 | Notes cut within one line (a label and its value, a tip cut at its comma like a list) or ending mid-sentence are joined | "זמן הכנה:" and "50 דקות" were two notes; the evaluation now reports such splits apart from missing information. |
| 2026-10-25 | "Used only in the steps" is found by the backend from a general list of ingredient words (`ingredient_words.py`, written without looking at the cases), as well as from the model's claims; what the dish is served with ("מגישים עם אורז") is left out | The model noticed 3 of 6 source gaps. On all 469 saved drafts the word list pointed out no ingredient that the draft listed; the 6 it raised beyond the known gaps were all ingredients the model's draft had dropped. |
| 2026-10-25 | A source recipe that omits an ingredient is a *source gap* in the evaluation, apart from extraction mistakes; "all checks passed" counts minor findings and required review points | The vanilla torte's strawberries were counted as a missed ingredient although the source never lists them; "all checks passed" had ignored minor failures. |
| 2026-10-25 | Clearer category descriptions (migration 0003 replaces a description only while it is still the starter text) | Measured on the same 50 drafts: 43 right and 7 wrong instead of 38–40 and 8–9, no dessert left unresolved, and the salted honey tart under desserts. A description the person changed is never overwritten; the migration's backup runs first. |
| 2026-10-25 | A section title ("מצרכים", "Ingredients") is never a group name, also beside other groups | It named the main group in two cases with a second, real group. |
| 2026-10-25 (2) | **Recognition apart from classification**: the local model's first request labels the passages and says whether the text is a recipe with no categories in view (`REFERENCE_LABELING_PROMPT`, `ReferenceLabels`); the category comes only from the second request, and a failed category request leaves the recipe unclassified | The user's drink caption was refused twice as "not a recipe". Its first decision, `is_recipe`, was close to a coin flip with the categories in the request: false in 8 of 12 imports (P(true) 0.10–0.80); without them true in 12 of 12 (P(true) at least 0.995). Other drinks and the restaurant review were unaffected (1.00 either way). No second check was added: with this cause removed, none was needed for that caption. |
| 2026-10-25 (2) | "Not a recipe" from the model is overruled only by both ingredients and steps in its labels | Ingredients alone (a shopping list) must not become a recipe; the case that motivated the rule had five ingredients and a step. |
| 2026-10-25 (2) | A colon cuts a line only after a label of at most five words; a sentence that ends in a colon keeps its list | An introduction ("…the secret turned out simple: salt, a lot of garlic and no vinegar") became two ingredient lines beside the real list (case 26). A list after a rejected introduction label is also kept out when the recipe has its own list. |
| 2026-10-25 (2) | A passage labeled a heading that ends a sentence is a step (or an ingredient); a title passage that is only a label takes the rest of its line; the prompt says a title names the dish and an introduction that mentions it is not one | "מחממים תנור מראש." was a heading (case 18); the title was "ארוחת בוקר של שישי" without the dish (case 14), or an introduction sentence (case 24). |
| 2026-10-25 (2) | Categories by the user's meaning (migration 0004): sweet desserts, dairy desserts included; generally savory dairy-based meals; generally meat- or poultry-based main dishes; no clear fit stays unclassified. The classification prompt says a category's description decides over its name, and the dish summary names what it is mainly made of | Measured on the same 60 drafts against the re-annotated expectations: 54 right, 5 wrong, 1 unresolved; the user's descriptions with the previous wording 46–49 right; the previous descriptions 44. The name "בישולים" (cooked dishes) had drawn vegetarian dishes. |
| 2026-10-26 (9) | Media files are content-addressed (sha256) and reference-counted by their attachments; downloads happen right after the post's page is read, before the database is written, and never fail an import | Instagram's media addresses expire, so the files are saved at once and shown from here. Recipe copies share files without copying them, and removing one never breaks another. The database is not held during minutes of downloads. |
| 2026-10-28 (2) | The home page is a gallery (design direction B, "גלריה בהירה", chosen from two browser previews): a top bar, a compact "ייבוא מתכון מקישור" strip (on a phone, behind its button), the filters, then the cards; one recipe per page | The recipes are the page, not a sidebar. Rubik is bundled (`@fontsource-variable/rubik`), so the page still loads nothing from the internet. |
| 2026-10-28 (2) | The page's place is kept in the address after "#" (`#/recipes/12`), with `pushState`, without a router library | The browser's back button returns from a recipe to the gallery (essential on a phone), and a reload stays on the recipe. Leaving unsaved changes asks first, the back button included. |
| 2026-10-28 (2) | "Already cooked" is a boolean of its own (`recipes.cooked`), changed only by `PUT /api/recipes/{id}/cooked`; every existing recipe starts unmarked | It is about you, not the recipe: not a category, not a draft status, not an edit (so "updated" stays). Nothing is guessed from other data. |
| 2026-10-28 (4) | Recipe websites: the page's Schema.org recipe data is copied word for word into the draft, and the model only classifies it; without recipe data the page's main text goes through the usual extraction | The site's own data is the most faithful source: nothing to mis-copy, and seconds instead of a minute. The model is still the only one choosing a category, by the same rules. |
| 2026-10-28 (4) | One link endpoint chooses the importer by the host name; the website reader checks every address (before connecting and after), sends an honest User-Agent and runs no scripts | Pasting any link must never reach this computer or the home network (SSRF). Sites that block such readers are reported as blocking, not worked around; pasting the text always works. |
| 2026-10-28 (4) | A page-text draft with no ingredient lines or no steps is refused as incomplete, and a bot-check page as blocked | Seen live: a page whose ingredient lists are drawn by its scripts, and a site that answered with a robot check. A half recipe saved as a draft looks complete enough to trust. |
| 2026-10-28 (5) | The local model's time limit is for the whole import (both requests together), 300 s by default, and a repeated identical import shares the running one | The limit was 600 s for each request, so one import could wait 20 minutes. 300 s is above the worst normal case on an 8 GB GPU (the whole 8k working memory at ~40 tokens a second is about 3.5 minutes). When it runs out the connection closes and Ollama stops generating (seen in its log: "cancel task"), so a retry never runs beside the old generation; a repeat sent while an import runs (a reload) gets that import's draft instead of a second one. The limit is clock time, time asleep included, and Ollama's answer is streamed so the clock is checked at every piece: a 17-minute import seen on 2026-10-28 was the laptop asleep (the model needed about 45 s), and the socket's own wait does not count time asleep, so the late answer was accepted after waking. Now an import whose time ran out while the computer slept stops at the first piece after waking and saves nothing (the page shows the timeout message). A page's own recipe data does not depend on the model: if only its category request runs out, it is saved unclassified, as when the model is unavailable. |
| 2026-10-28 (5) | Inside a page's main content, a block named like noise (print, widget, share...) that holds most of the content's own text is part of it; comments are removed first and never count | The name rule removed a recipe wrapped in a "print" area, and a page builder's "widget" boxes. Measuring the text outside links keeps related posts and share bars (mostly links) out; removing comments first keeps a long comment section from outweighing the recipe. |
| 2026-10-28 (3) | A card is two sibling buttons: one opens the recipe, the badge (`aria-pressed`) changes the mark; never one inside the other | A button inside a button is invalid and unpredictable for keyboards and screen readers. The badge shows only what was saved (no optimistic change), ignores clicks while saving, and when the filters hide the card a note offers "ביטול" and takes the focus. |
| 2026-10-28 (2) | A category's drawing and color come from its name (קינוח, בשרי, קליל, משק…) | A category you add looks like its kind without any setting; any other gets the utensils, an unclassified recipe the notebook. |
| 2026-10-28 | Fetching a post's media keeps the picture the card showed: a cover that was the default (the first picture) is kept as chosen when the post's items come before it | Found in the browser checks: an upload shown on the card would otherwise be replaced by the post's first item, although nothing was chosen. |
| 2026-10-26 (9) | Uploads are the raw request body, not a multipart form | One picture at a time needs no new dependency (python-multipart); the size limit is checked while reading. |
| 2026-10-26 (8) | The credit is a list of `{name, username}` (migration 0008); an import fills it from the post's data (`user.full_name`, `user.username`, `coauthor_producers`), and keeps that as read in `recipe_imports.source_details` | The person recognizes creators by name and handle; the handle gives the profile link. Retrieved data, not the model, says who made it. Editing the credit (when a post credits someone else) never changes what was retrieved. |
| 2026-10-26 (7) | Duplicate Instagram links are checked on the server, before anything is fetched, for links and for pasted text with a link; the same post is the same shortcode; a match stops the import with the list of recipes, and `allow_duplicate` imports another copy | Enforced where the import happens, so no client can skip it and nothing is fetched twice by accident; never an overwrite and never a block. Both places a link can live count: the read-only original and the editable sources. |
| 2026-10-26 (6) | Search and filters run in the page on the recipes already loaded (`recipeFilters.ts`): title and ingredient lines, every word, after removing niqqud, invisible marks and quote marks; a top-level category includes its subcategories | A personal notebook holds hundreds of recipes, not millions: the list is already in the page, so filtering it there is instant and needs no new endpoint. A server-side search can come if the notebook grows. |
| 2026-10-26 (5) | Categories are created and edited by the person in the page (`POST`/`PUT /api/categories`): name and description only, the parent fixed once created, names unique among siblings, no delete yet | Recipes point at the pair (category, subcategory), so moving a subcategory or deleting a category would need a decision about its recipes. The descriptions are read at every import, so a new description guides the next classification. |
| 2026-10-26 (4) | Dessert subcategories "קינוחים רגילים" and "קינוחים בריאים" (migration 0007); the model picks a subcategory only when one clearly fits, and an invalid subcategory now keeps the category instead of leaving the recipe unclassified | The user's own organization: "healthy" is a style of dessert (dates, oats, nuts, almond flour, nut butter), judged by the whole recipe, not a nutritional verdict. A dessert with an unclear style is still a dessert. |
| 2026-10-26 (3) | An introduction is not content: a question alone on its line before the ingredients, a question labeled a heading, or a sentence labeled a heading before the list starts (with no amount) starts that list and stays in the original only. Other sentences labeled a heading become what they head. Optional labels are purpose labels; a meaningful note label keeps its whole line as one note; purely social lines are dropped | A real caption's "אז מה צריך לכל הטוב הזה?" became step 1: labeled a step heading, it was turned into a step by the heading-sentence rule (for "מחממים תנור מראש.") before what it heads was looked at. Its "אופציונאלי:" label was lost, its vegan egg replacement became an ingredient plus a stray "זה תחליף לביצה" note, and "תהנו" a note. Rebuilt from the saved answers of the two full runs: no other draft changed except three sign-offs removed. |
| 2026-10-26 (2) | Instagram links: the post page in a fresh logged-out browser first; the embed view over HTTP once, only when the post page gave no complete caption and Instagram did not say "unavailable", "no caption" or "wait"; a preview is never imported as complete | milestone 1's recommendation. Instagram's own answers are final (asking another page would not change them, and after "wait" must not). A preview cannot be shown complete, so the person compares it with the post. |
| 2026-10-26 (2) | One request reads the post and extracts the recipe; failures carry the address and any caption read | The caption saved with the draft is exactly what the server read (the page never sends it back as "Instagram's"); the page can still offer the paste fallback with what was read. |
| 2026-10-26 (2) | The caption and the post's address are part of the read-only original (`recipe_imports.url`, `retrieved_from`; migration 0006); the editable source also gets the address and the creators | The person may change the source; the original records what was imported and from where. |
| 2026-10-26 (2) | Playwright runs in `asyncio.run(..., loop_factory=ProactorEventLoop)` inside the import's worker thread | The server's own loop under `uvicorn --reload` on Windows cannot start the browser (milestone 1 finding); verified live in a `--reload` server. |
| 2026-10-26 | A composed title names the dish itself (what it is, its main ingredients) in the text's own spelling, from the introduction too, never the occasion, story or hype; a title that starts no line of the text is flagged as composed whatever the model claims | Titles such as "משקה טרנדי לכבוד היום האחרון של הקיץ" named the occasion instead of the drink. Measured on 13 cases, two runs each: see docs/extraction-quality.md. |
| 2026-10-25 (3) | The user's reorganized categories (migration 0005): "בישולים" renamed "ארוחות בשריות" (meat and poultry meals), "ארוחות קלילות" for savory dairy **or egg** meals, "משקאות" added at the user's request (drinks, smoothies, coffee drinks, lemonade; sweet or milk drinks too). The descriptions name concrete dishes and avoid the double meaning of "מלוח" (savory or salty); the no-fit example in the prompt no longer names a drink | Measured on the same 68 drafts with the category request alone: 65 right, 2 wrong, 1 unresolved with the chosen descriptions; 59 to 61 with plainer ones. A yes/no answer per category (59–60) and quoting the matching description words (60, forcing a category onto pickles and soup) were worse. |
| 2026-10-25 (2) | The evaluation reports import success apart from accuracy within drafts, and a line or step kept as a group heading as misplaced | A refused recipe has no lines to check: without its own count it would vanish from the per-area numbers. |
| 2026-10-20 | Ollama requests send `"shift": false` | Without it, an answer that fills the working memory makes Ollama drop the oldest half (the instructions and the text) and continue: one runaway answer ran 28,000 tokens until the 10-minute timeout. Now it stops at the limit and the import reports it. |
| 2026-10-20 | No compact-JSON request, although it is about 30% faster | Measured on the 20 cases: more wrong quantities in both modes (references 16 instead of 11) and fewer drafts without corrections (8 instead of 10). Quality first. |

## Known limitations

- **Website imports are a first version.** Tested on the pages in
  [website-import.md](website-import.md); other sites may fail in other ways. Not supported: pages that
  build their content with scripts (refused as incomplete or as having no recipe), sites that block
  readers that are not browsers or show a robot check (reported as blocking), pages behind a login or
  a paywall, several recipes on one page without one named (refused as ambiguous), a site's other
  pictures and its videos (only the main picture is saved), and ingredient groups (Schema.org lists
  ingredients without them: they come as one list). Pasting the recipe's text works for all of them.

- **"Already cooked" is a yes or no.** No date, no count, no rating; a later version could add them
  next to it without changing the mark.
- **A category's drawing follows its name.** Renaming "קינוחים" to something without "קינוח" gives
  its recipes the general utensils drawing and color.
- **Filters are not remembered.** The search and the filters start empty after a reload (the open
  recipe is remembered, in the address).

- **Categories cannot be deleted or moved yet.** A subcategory stays under the category it was created
  in; removing a category needs a decision about its recipes (milestone 6).
- **Search looks at titles and ingredient lines only**, as plain text (every word, anywhere): not the
  steps or notes, and no Hebrew word forms beyond "part of a word" ("תפוח" finds "תפוחים", but "ביצה"
  does not find "ביצים").
- **Duplicates are recognized by Instagram links only** (the post's shortcode). The same recipe
  pasted without a link, or from another post, is not recognized as a copy.
- **The dessert subcategory can follow one ingredient word** rather than the whole recipe: a date cake
  and oat cookies built on flour, sugar and butter were put under "קינוחים בריאים" (docs/extraction-quality.md).

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
- **A local model's wrong category is not caught.** The backend can check that a category exists,
  not that it fits: Qwen3 8B sometimes puts a dairy pasta or a fish dish under "ארוחות בשריות". The review
  screen shows the chosen category, and the person decides; an unclassified recipe can be saved.
- **Quantities follow fixed rules, not judgment.** `quantity.py` knows the common Hebrew and
  English amounts and units; an unusual unit or wording gives no quantity (never a wrong one
  invented), and the line itself is always complete. Words that look like amounts in an
  unexpected place could be taken; the 202 expected quantities had no such case.
- **Roles are the model's judgment.** An introduction or a call to action labeled as a tip ends up
  in the notes (calls to action are flagged); a sentence that goes on to the next line may become
  two steps. Nothing is lost or reworded, but the draft can need moving or deleting. Run to run the
  labels vary (the same model, temperature 0, on a GPU).
- **"Used only in the steps" knows only common ingredient words** (about 300 ingredients, in
  Hebrew and English, with their usual forms) and the model's claims. An ingredient outside the list,
  named differently in the steps, or used in a clause that serves the dish with something else
  ("מגישים עם אורז") is not pointed out. Missing information is checked for baking only
  (temperature, time).
- **Reference mode with Claude is untested here.** Its schema has one property per passage, named
  by the passage's opening words; no API key was available to check it against the Claude API.
  If it fails, `RECIPES_EXTRACTION_MODE=text` restores the earlier request.

- **Pictures and videos:**
  - Each post format was verified live except a single-image post, which is tested with fixtures only
    ([instagram-feasibility.md](instagram-feasibility.md#pictures-and-videos-2026-10-26)).
  - Fetching for an existing recipe reads the post again, with the same limits as an import: a
    private, deleted or login-only post, or Instagram asking to wait, stops it with a message, and
    nothing is retried automatically.
  - Videos are kept as Instagram serves them (MP4), without conversion. Edge, Chrome and Firefox on
    Windows play them; a browser without H.264 support (some Linux builds of Chromium) shows only the
    still. Instagram gives no caption file, so the videos have no captions; the post's text is in
    "הטקסט המקורי".
  - A video's size is known only while it downloads: up to three of its addresses are tried, and a
    video over 150 MB keeps only its still, with a link to the post. Long reels take disk space (the
    browser check's three posts and two uploads: 22 files, 18.6 MB).
  - Uploads are pictures only, one file per request, and come after the post's items; the order cannot
    be changed. Stories, highlights and share links (`instagram.com/share/...`) are not supported.
  - Changing a recipe's Instagram source does not remove media fetched from the earlier post; "הסרה
    מהמתכון" removes items one by one. A fetch cannot be cancelled.
  - Back up `media/` together with `recipes.db` (README, "Settings and where data lives").

## Notes for upcoming milestones

- **Milestone 5:**
  - **Reuse the extraction** (done for Instagram). A fetched page text goes through the same
    extractor, `make_draft` and `create_import`; `recipe_imports.kind` gains `website` and
    `screenshots`.
  - **Screenshots** are sent as image blocks in the same request, in order; the source check in
    `review.py` cannot compare with an image, so their lines need another review signal.
  - **Add evaluation cases** for each new source kind before relying on it.
- **Milestone 5 (Windows):** `uvicorn --reload` (and `fastapi dev`) runs on an event loop that cannot
  start subprocesses, and Playwright then fails with an empty `NotImplementedError`. The Instagram
  import runs Playwright with `asyncio.run(..., loop_factory=asyncio.ProactorEventLoop)` inside the
  import's worker thread (`retrieve_caption_blocking`), verified in a live `--reload` server.
