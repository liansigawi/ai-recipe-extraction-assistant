# Importing recipe pages from websites (first version, 2026-10-28)

One field, "ייבוא מתכון מקישור", takes Instagram posts and recipe pages. The backend chooses the
importer by the address's host name (`POST /api/imports/link`); a model never makes that choice. How a
page is read: [architecture.md, "Import flow (a recipe website)"](architecture.md#import-flow-a-recipe-website).

## What was tested live

On 2026-10-28, through the app (the import strip and the API) on a separate test copy of the notebook,
with the local model (Ollama, qwen3:8b). Each page was read once or twice, a few seconds apart.

| Page | Language | Path | Result |
|---|---|---|---|
| hidabroot.org, oatmeal chocolate chip cookies (`/article/1214716`) | Hebrew | JSON-LD | Draft in 2.5 s: 9 ingredient lines and 8 steps word for word, servings "45 עוגיות גדולות או 70 קטנות", times as a note, credit "אורית גרוסקוט", the WebP main picture as the cover; the model chose קינוחים / קינוחים בריאים. Saved through the review screen. |
| mako.co.il, chocolate birthday cake | Hebrew | JSON-LD | Read correctly at the first request (7 ingredient lines, 10 steps, author קרן אגם, times, picture). Later requests got a Radware "are you a robot?" page: now reported as **blocked**, without asking the model. |
| food.unl.edu, banana bread | English | Microdata | 8 ingredient lines and 7 steps word for word, servings "12 servings"; the model left it unclassified ("not clearly one category"); no picture in the page's data. |
| srugim.co.il, green shakshuka | Hebrew | Page text | The article's text (1,826 characters) → the extraction → 9 ingredient lines and 14 steps; classified as ארוחות קלילות; its picture saved; credit "חדשות סרוגים". Saved through the review screen. |
| oryana.coop, banana bread | English | Page text | The recipe's text (606 characters) → the extraction → 7 ingredient lines and 5 steps; left unclassified; credit "Oryana"; picture saved. |
| oogio.net, homemade chocolate milky (`/homemade_milky/`) | Hebrew | Page text | At first **"no recipe"**: the theme wraps the whole post in layout wrappers named `penci_is_nosidebar` and `theiaStickySidebar`, so the "sidebar" rule removed the recipe with them; the model got 104 characters (the title and a CSS rule) and rightly found no recipe. Fixed (the main content and its wrappers are never noise): 2,835 characters → 3 ingredient groups (לפודינג שוקולד 8, לקצפת וניל 4, לקישוט 1), 2 step sections (9 and 3 steps), 5 notes (the dairy-free version among them); the introduction, the links to other recipes and the request to share left out; credit "נטלי לוין", picture saved; the model chose קינוחים / קינוחים בריאים. 52 s. Saved through the review screen. |
| adikosh.co.il, coffee and chocolate cake | Hebrew | Page text | Unchanged by the fix (same text): 2 ingredient groups (לעוגה 8, לבלילת השוקולד 2), 3 step sections, the tips as notes, credit "עדיקוש", picture; קינוחים / קינוחים רגילים. 35 s, as "another copy" after the duplicate notice. |
| maariv.co.il, shakshuka article | Hebrew | Page text | **Refused as incomplete**: the page's ingredient lists are drawn by its scripts (`BAILOUT_TO_CLIENT_SIDE_RENDERING`), so its text had steps without ingredients. (The page also has four variations.) |
| ynet.co.il/laisha, pan quiches | Hebrew | Page text | **No recipe**: the page sends 60 characters of text (it builds itself with scripts). |
| recipes.heart.org, banana bread | English | — | **Blocked**: HTTP 403 to a reader that is not a browser. Pasting the text then saved it with the page as its source. |
| mako.co.il, a page that does not exist | Hebrew | — | Answered with the same robot check (blocked), not a 404. A 404 is tested with fixtures. |

Also live: the same food.unl.edu page again, as `http://` with a tracking parameter → "הדף הזה כבר
במחברת" before anything was read; an Instagram post already in the notebook → its duplicate warning,
then "another copy" read live as before (caption, credit, 3 pictures and videos).

## Tested with fixtures only (offline tests)

Every address rule (private, loopback, link-local and shared ranges, IPv6 and IPv4-mapped addresses,
`.local` names, other ports, credentials in the address), redirects to a private address, a host that
resolves to one, too many redirects, the connected address check (failing closed), 404, 429, 500,
timeouts, non-HTML answers, pages over the size limit (by their header and while streaming), a
windows-1255 page, JSON-LD in an `@graph`, as a list, with `HowToSection`s, HTML entities and tags,
numbered steps in one string, microdata, two recipes (one named by the page's heading, or none:
ambiguous), recipe data without ingredients or steps, a blog page's navigation/ads/related
posts/comments, a post inside layout wrappers named for a sidebar (oogio.net's theme, and the common
`content-sidebar-wrap`) with ingredient groups as `<br>` lines and `<h1>` section headings, a cut very long page, the canonical address, the picture failing or not being a
picture, a model that cannot classify, and imports without a model.

## Limits

- **Sites that block non-browser readers** (HTTP 401/403/429, or a robot check) are reported as
  blocking. The reader does not pretend to be a browser and does not retry.
- **Pages built by scripts**: whatever is not in the HTML the site sends is not seen. Such pages are
  refused (incomplete, or no recipe) rather than imported half-filled.
- **Several recipes on a page**: with recipe data, the one the page's heading names, or none
  (ambiguous). In page text, the extraction takes the main recipe and may flag "כמה מתכונים בטקסט".
- **Ingredient groups** ("לבצק", "למלית") are not part of Schema.org's ingredient list: a page's
  recipe data gives one list. Steps keep their sections.
- **Only the main picture** is saved; a page's other pictures and its videos are not.
- **The text extraction is a heuristic**: it removes what the page's markup calls navigation,
  comments, ads, sharing and related posts. The element that holds the main content (the largest
  recipe or post container, else the largest article, else `<main>`, else the heading) and the
  wrappers around it are never removed, whatever their names. A noise-named block *inside* the
  content (say, the recipe wrapped in a "print" block) is still removed, and small clutter can stay
  (a view counter, captions, a run-together tag list); the model leaves those out. The review screen
  shows exactly what was read.
- **The local model's speed**: once, with the laptop on battery, the model generated 1.75 tokens a
  second instead of about 40, and one page took 17 minutes; the same request took under a minute
  before and after. A very slow import says more about the computer at that moment than about the page.
- Login pages, paywalls and pages over 3 MB are not read.
