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

## 2026-11-03: recipe data checked against the page

A Foody recipe ("הנודלס הירוק", `foody.co.il/foody_recipe/...`) came in with one long step that began
"אופן הכנה" and ended "...שיהיה בתיאבון![caption id=״attachment_151593״ ...] ... צילום: דר טייב[ caption]בשיתוף
עם טעם הטבע". Traced: the import used the page's JSON-LD (no model wrote the steps; the model only chose
the category), and the JSON-LD itself had `recipeInstructions` as that one string, its quotes already ״ and
its closing slash already gone. The page shows `<h2>אופן הכנה</h2>`, an `<ol>` of three steps, the photo as a
`<figure>` with its caption, and `<p>בשיתוף עם טעם הטבע</p>`; its ingredients are in two groups ("רוטב",
"נודלס מוקפץ"), each line with a comment ("או סילאן", "לא חובה") that the JSON-LD drops. Nothing was lost
in saving or showing: the importer trusted the data as given.

Now the importer checks the data against the page's own lists (`checked_with_page`): the three list items
are the steps, in the page's words; the two groups and their lines (comments included) are the
ingredients; the caption and the sponsor are in no step; the credit is still the recipe data's author. A
list that misses any word of the steps (a paragraph between items, say) leaves the data as it is, never
split by guessing. Without matching lists, a `[caption]...[/caption]` (or `[embed]`, `[gallery]`...)
shortcode and a line that only names a sponsor are still taken out of the steps.

Checked on pages saved once each (2026-11-03), old code against new: the Foody recipe above and two more
Foody recipes (1 step became 5 and 7, with their groups); hidabroot.org (JSON-LD), food.unl.edu
(microdata), adikosh.co.il, oogio.net and ronyohananov.com (page text): unchanged. A saved recipe is never
changed by this: importing the page again makes a new draft.

## 2026-11-04: a page builder's template read whole

coralhota.co.il, a raspberry and white chocolate biscuit cake (`/recipes/עוגת-ביסקוויטים-פטל-ושוקולד-לבן/`),
was refused as incomplete. Traced: the site sent the whole page (369,502 characters, the ingredient lists in
it); it has no recipe data, so its text was read. The page is an Elementor template for one post
(`data-elementor-type="single-post"`), with the title, the introduction, each ingredient list and the notes
in boxes of their own; the box named "post content" (`elementor-widget-theme-post-content`) holds only the
method. That box was taken as the main content, and the ingredient boxes outside it were also removed as
"widgets" (Elementor names every box a widget). The model got 1,308 characters, the steps without any
ingredient, and the draft was rightly refused. No script was involved.

Now a single-post template is the main content as a whole, and the word "widget" in Elementor's own box
names is not taken as noise; what a box is for still is (its comments, sharing buttons, a grid of other
posts, `jet-listing-grid`). The same page gives 2,973 characters: the four ingredient groups (with the
pan size and the optional items), the steps in order, and the notes (the substitution among them). The
refusal stays for a draft without ingredients or steps; its message no longer guesses a cause ("לא
הצלחנו לחלץ מהעמוד מתכון מלא").

Checked on pages saved once each, old code against new: two Foody recipes, the Foody noodles above,
hidabroot.org, food.unl.edu, adikosh.co.il, oogio.net and ronyohananov.com read the same text as before.

## Tested with fixtures only (offline tests)

Every address rule (private, loopback, link-local and shared ranges, IPv6 and IPv4-mapped addresses,
`.local` names, other ports, credentials in the address), redirects to a private address, a host that
resolves to one, too many redirects, the connected address check (failing closed), 404, 429, 500,
timeouts, non-HTML answers, pages over the size limit (by their header and while streaming), a
windows-1255 page, JSON-LD in an `@graph`, as a list, with `HowToSection`s, HTML entities and tags,
numbered steps in one string, microdata, two recipes (one named by the page's heading, or none:
ambiguous), recipe data without ingredients or steps, a blog page's navigation/ads/related
posts/comments, a post inside layout wrappers named for a sidebar (oogio.net's theme, and the common
`content-sidebar-wrap`) with ingredient groups as `<br>` lines and `<h1>` section headings, the recipe
inside a "print" area or a page builder's "widget" box (with related posts and a long comment section
beside it, both left out), an Elementor single-post template with the ingredients outside its "post
content" box (comments, a grid of other posts and the site's header and footer left out), a cut very long page, the canonical address, the picture failing or not being a
picture, a model that cannot classify, and imports without a model.

## Limits

- **Sites that block non-browser readers** (HTTP 401/403/429, or a robot check) are reported as
  blocking. The reader does not pretend to be a browser and does not retry.
- **Pages built by scripts**: whatever is not in the HTML the site sends is not seen. Such pages are
  refused (incomplete, or no recipe) rather than imported half-filled. A refusal as incomplete says only
  that the draft had no ingredients or no steps: the cause can also be the text selection (below).
- **Several recipes on a page**: with recipe data, the one the page's heading names, or none
  (ambiguous). In page text, the extraction takes the main recipe and may flag "כמה מתכונים בטקסט".
- **Ingredient groups** ("לבצק", "למלית") are not part of Schema.org's ingredient list: they come from
  the page's own lists when those show every line of the recipe data in order; otherwise one list.
- **Only the main picture** is saved; a page's other pictures and its videos are not.
- **The text extraction is a heuristic**: it removes what the page's markup calls navigation,
  comments, ads, sharing and related posts. The element that holds the main content (the largest
  recipe or post container, else the largest article, else `<main>`, else the heading) and the
  wrappers around it are never removed, whatever their names; nor is a block inside it that holds
  most of its text outside links (the recipe in a "print" area, a page builder's "widget" box).
  An Elementor template for one post is read whole, its boxes included. Still removed: a recipe that
  another page builder splits over *several* boxes named like noise, each holding less than half of the
  text, and a recipe inside a block named for comments. Small clutter can
  stay (a view counter, captions, a run-together tag list); the model leaves those out. The review
  screen shows exactly what was read.
- **The local model's time**: one import waits for the model at most `RECIPES_OLLAMA_TIMEOUT_SECONDS`
  (300 s by default, both of its requests together, in clock time: time asleep counts); then the
  request is stopped and nothing is saved. An import seen taking 17 minutes on 2026-10-28 was the
  laptop going to sleep three seconds after the import started (Windows' power log: asleep 15:54:48
  to 16:10:38); the model itself needed about 45 seconds. If the computer sleeps past the limit, the
  import stops as soon as it wakes and the page says the time ran out; try again. A page's own recipe
  data is still saved (only its category comes from the model), unclassified if that request ran out.
- Login pages, paywalls and pages over 3 MB are not read.
