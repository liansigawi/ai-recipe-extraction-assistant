# Instagram import: feasibility findings (milestone 1)

**Question from the brief:** can a local automated browser retrieve the *full* caption of a public
Instagram post, rather than a truncated preview? What worked, what failed, and was login required?

**Answer (2026-10-18, from this computer):** yes, for all three sample posts, with no login. A
headless, logged-out Playwright browser got the complete caption from the post's own data, which
Instagram renders into the page. A plain HTTP request to Instagram's public *embed view* also
returned the complete caption. That view serves an older snapshot and is meant for embedding (see
below). This is evidence from a few small runs on one day, not a reliability guarantee (see
[Limits](#limits-of-this-evidence)).

## What was run

| | |
|---|---|
| Runs | `20261018-135240` (13:52–13:54 +03:00): 3 posts × 4 strategies = 12 page loads, 6 s apart, Python 3.14.0. Captured with an earlier version of the capture code, which also tried to click a "more" toggle; it never fired. |
| | `20261018-140600` (14:06): 1 nonexistent post × 4 strategies = 4 page loads ([failure path](#failure-path-a-post-that-does-not-exist)) |
| | `20261018-142944` (14:29): Python 3.14.8, 3 posts × the 2 strategies the importer would use = 6 page loads, 10 s apart |
| | `20261018-144745` (14:47): **the final code**, after the review fixes (overall deadlines, HTML read first), same 6 page loads |
| | `20261019-140137` (next day): `http-embed` only, 3 page loads, after the HTTP client moved from HTTPX to its maintained fork `httpx2` (User-Agent `python-httpx2/2.14.0`): 3 of 3 complete captions |
| Requests | 31 page loads in total, one at a time, no retries. Each browser load also fetched the page's scripts and images and made about 4 GraphQL calls. |
| Machine | Windows 11 (10.0.26200), this computer's normal internet connection, no VPN |
| Browser | Playwright 1.64.0, bundled Chromium 156.0.8078.4 (headless shell), reporting itself as `HeadlessChrome` |
| HTTP client | HTTPX 0.28.1 with its default User-Agent `python-httpx/0.28.1`; httpx2 2.14.0 (`python-httpx2/2.14.0`) for the last run |
| Identity | Fresh browser profile, no cookies, no login, no User-Agent disguise, no stealth plugins, no calls to private APIs. Both clients asked for English (en-US) pages, which the preview parser's date format depends on. |
| Command | `uv run python -m scripts.probe_instagram` (from `backend/`) |
| Artifacts | `data/instagram-probe/<run>/` (git-ignored): `run.json`, `summary.md`, `summary.json`; per strategy `page.html`, `capture.json` and `analysis.json`, plus `screenshot.png` for browser strategies |

### Strategies

| Strategy | What it does |
|---|---|
| `browser-post` | Playwright loads `https://www.instagram.com/p/<code>/` and keeps the final HTML plus the JSON responses the page itself requested |
| `browser-embed` | Playwright loads the public embed view `https://www.instagram.com/p/<code>/embed/captioned/`, the page websites show when they embed a post |
| `http-post` | Plain HTTP GET of the post page (no JavaScript) |
| `http-embed` | Plain HTTP GET of the embed view (no JavaScript) |

## Results

Every load of the three posts returned HTTP 200. None redirected to `/accounts/login` or `/`,
contained a password field, or showed a rate-limit or "isn't available" message.

| Post | Creator | Caption | `browser-post` | `browser-embed` | `http-embed` | `http-post` |
|---|---|---|---|---|---|---|
| [Cm1mCdCpSzJ](https://www.instagram.com/p/Cm1mCdCpSzJ/) | ritakadosh_ | 2,126 chars, 47 lines | ✅ full | ✅ full | ✅ full | ⚠️ preview only |
| [DPbKEn-CnUt](https://www.instagram.com/p/DPbKEn-CnUt/) | ritakadosh_ | 920 chars, 31 lines | ✅ full | ✅ full | ✅ full | ⚠️ preview only |
| [DANUmOOIcRM](https://www.instagram.com/p/DANUmOOIcRM/) | lioroooosh, with alehonline (collaboration post) | 2,034 chars, 31 lines | ✅ full | ✅ full | ✅ full | ⚠️ preview only |

The two later runs (`20261018-142944`, and `20261018-144745` with the final code) repeated ✅ for
`browser-post` and `http-embed` on all three posts, with byte-identical captions.

- ✅ **full**: the caption came from the post's own data object, so it is complete by construction.
- ⚠️ **preview only**: `http-post` got only the meta tags (`description`, `og:description`, `og:title`).
  For these posts the preview held the whole caption, but a preview cannot be *shown* to be complete,
  so the importer marks it `caption_incomplete`.
- All three are Reels (`product_type: "clips"`) shared as `/p/` links. Two of the three embed views
  are `copyright_blocked` (licensed music): they show "Watch on Instagram" instead of a player but
  still carry the full caption and data.
- **End-to-end capture time** includes launching and closing a fresh browser and taking a
  screenshot, so it is not page-load time:
  - first run: `browser-post` 5.1–6.6 s, `browser-embed` 2.6–2.8 s, plain HTTP 0.8–1.1 s;
  - later runs: `browser-post` 3.4–6.5 s (the first capture of a run is the slowest), `http-embed` 0.7–1.1 s.

### How "full caption" was established

1. **Source.** The text comes from the post's own data object, matched by shortcode *and* post
   fields (`id`/`pk`), not from a preview field:
   - post page: `<script type="application/json" data-sjs>` → `…/xig_polaris_media/if_not_gated_logged_out` → `caption.text`;
   - embed view: the `"contextJSON"` string inside a script → `gql_data.shortcode_media.edge_media_to_caption.edges[0].node.text`.

   On all three posts the wrapper's `gating_ruling` was `null`, meaning the post was not gated.
2. **Agreement.**
   - Two separately served pages (the post page's data and the embed view's data) gave
     byte-identical text.
   - The embed's rendered caption block comes from the same response as its data, and it matches
     after trimming two leading newlines.
   - The `og:description` preview also matched exactly.

   Agreement shows consistency, not completeness. Completeness rests on the source.
3. **Length.** The longest caption, 2,126 characters, is close to Instagram's 2,200-character limit
   for captions.
4. **Manual reading.** Each caption contains its complete text, including every ingredient list and
   the preparation steps, and ends with a natural closing line:
   - Cm1mCdCpSzJ (vanilla torte) ends with hashtags;
   - DANUmOOIcRM (salted honey tart) ends with a collaboration credit;
   - DPbKEn-CnUt (shoulder roast with ptitim) ends with a "send this to a friend" sign-off.

### Fidelity cases these captions contain

They become evaluation cases once AI extraction exists (milestone 4). The formal evaluation set is
built in milestone 7.

- **Cm1mCdCpSzJ**
  - cake, cream and syrup ingredient groups;
  - the pan size given in the method header;
  - `50-60 דקות על 150 מעלות`;
  - **strawberries appear only in the title and the method**, never in an ingredient list. The brief
    says to surface such an ingredient for review.
- **DPbKEn-CnUt**
  - ingredients without quantities (`מלח פלפל`, `פפריקה מתוקה`);
  - pressure-cooker **or** regular-pot cooking times;
  - reuse of the meat's cooking liquid (`2 וחצי כוסות מהמים בהם התבשל הבשר`).
- **DANUmOOIcRM**
  - `115 גר’ חמאה רכה` in the dough and `115 גר’ חמאה מומסת` in the filling. The caption writes the
    unit with ’ (U+2019) here but with ׳ (U+05F3, geresh) in `120 גר׳ שמנת מתוקה`; extraction must
    keep each character as written;
  - `|`-marked groups;
  - an alternative (`תמצית / מחית וניל`);
  - a topping without a quantity (`לציפוי - מלח מאלדון`);
  - time ranges.

### What a logged-out visitor sees

The post page renders the post and its caption under a dismissible "Never miss a post from …
Sign up / Log in" dialog with a Close button (see `browser-post/screenshot.png`). That is a sign-up
prompt, not a login wall: the caption is on the page and in its data.

One of the page's own GraphQL responses included the experiment flags
`ig_desktop_dynamic_blocking_dialogs_launch: "true"`. This suggests (an inference) that Instagram is
testing *blocking* dialogs for logged-out desktop visitors. If so, this observation could change.

## Failure path: a post that does not exist

To see real failure pages instead of guessed ones, the probe ran once on `AAAAAAAAAAA`. It is a
valid shortcode format that decodes to media ID 0, so it cannot exist.

| Strategy | HTTP | What the page showed | Outcome |
|---|---|---|---|
| `browser-post` | 200 | Title "Post isn't available • Instagram"; "The link may be broken, or the profile may have been removed."; route `comet.igweb.PolarisErrorRoute` | `unavailable` |
| `browser-embed` | 200 | An `EmbedBrokenMedia` block: "The link to this photo or video may be broken, or the post may have been removed." | `unavailable` |
| `http-embed` | 200 | Same as `browser-embed` | `unavailable` |
| `http-post` | 200 | Only the word "Instagram" visible, but the page data names the route `comet.igweb.PolarisErrorRoute` | `unavailable` |

**Instagram answers HTTP 200 even for a missing post**, so the importer relies on page markers
instead of status codes. The `EmbedBrokenMedia` and error-route markers were added to the analyzer
after this run, and the saved run was re-analyzed offline.

Other tools report that valid posts briefly showed "isn't available" to logged-out visitors in June
2026. The interface should therefore say "Instagram says this post isn't available (deleted,
private, or temporarily unavailable)", not "deleted".

## The embed view is an older snapshot

- **Older counts.** Within the same minute, and even within one HTML response, the embed view and
  the `og:description` preview showed lower like counts than the post page's own data: 439 vs 444
  for Cm1mCdCpSzJ, and 3,764 vs 3,832 for DPbKEn-CnUt. They are served from a cached snapshot.
- **Edits may lag.** A caption edited recently might still show its old text there. That has not
  been tested; DANUmOOIcRM is marked `caption_is_edited: true`, and all sources agreed on it.
- **Less attribution.** The embed's data also lacks the co-author list that the post page's data
  carries.

## Corroboration from open-source tools (October 2026)

A research pass on 2026-10-18 read the current code and issue trackers of yt-dlp, instaloader and
gallery-dl, plus public captures from other projects. It made no Instagram requests. The links are
the pages the research reported reading; they were not re-checked line by line.

- yt-dlp's no-impersonation fallback (added 2026-07-01,
  [PR #17113](https://github.com/yt-dlp/yt-dlp/pull/17113)) reads exactly the post-page path found
  here: `__bbox.result.data.xig_polaris_media.if_not_gated_logged_out`
  ([extractor source](https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/yt_dlp/extractor/instagram.py)).
- instaloader 4.15.4 (2026-10-12) says Instagram renders public pages with the results of its GraphQL
  queries embedded in the HTML, even when it refuses anonymous API requests for the same data
  ([source](https://raw.githubusercontent.com/instaloader/instaloader/master/instaloader/instaloadercontext.py)).
  This matches the "Unauthorized logged out query" seen here.
- These tools use further failure signals, which were adopted in the analyzer **without having been
  observed here**:
  - a redirect to the homepage `/` counts as a login wall
    ([yt-dlp #17275](https://github.com/yt-dlp/yt-dlp/issues/17275));
  - the route `…PolarisCAAIGLoginHomepageRoute` means a login page served in place of the post
    ([2scraper page_parser](https://raw.githubusercontent.com/2scraper/instagram-scraper/main/page_parser.py));
  - `if_not_gated_logged_out: null` means a gated post (for example age-restricted);
  - GraphQL error `1675004` or "Please wait a few minutes before you try again" means rate limiting
    ([instaloader #2738](https://github.com/instaloader/instaloader/issues/2738)).
- **The embed data uses a legacy shape** (`shortcode_media`, `edge_media_to_caption`). Instagram
  retired that shape from its public query endpoint around 2026-06-27
  ([instaloader #2704](https://github.com/instaloader/instaloader/issues/2704)), and yt-dlp dropped its
  embed fallback the next day. The embed view still served it on 2026-10-18.
- **Friction is growing.** Since September 2026 the tools report partial "execution error" responses,
  `401 Please wait a few minutes`, and much stricter treatment of VPN, cloud and data-center IPs.
  One project measured a plain HTTP client being throttled after about 75 page loads in an hour,
  while a real browser on the same IP kept working.

## What failed or surprised us

- **Three analysis bugs, all fixed.** Each got a regression test, and the saved runs were re-analyzed
  offline with no new requests:
  1. `og:description` wraps the preview in invisible left-to-right marks (U+200E, after the date and
     at the end), which broke the preview pattern.
  2. The page's router parameters also carry the shortcode, with `"caption": null`. Without a check
     for real post fields, that object would be misread as "this post has no caption" on any page
     where no other caption is found. In this run that was the plain-HTTP post pages, while bug 1
     also hid the preview.
  3. A caption containing words like "too many requests" would have been reported as rate limiting,
     because the visible page includes the caption. Now a caption found in the post's own data wins
     over page-level warnings.
- **The page's own API calls carried no post data.** Each post page's four captured GraphQL responses
  were three experiment responses and one `"Unauthorized logged out query."` refusal. The post itself
  arrives already rendered into the HTML.
- **Plain HTTP of the post page gets less.** Its HTML had no post data object, only the meta tags. Other
  tools add browser navigation headers to get more; this project does not disguise its client.
- **Invisible direction marks inside a caption.** One of the three captions (Cm1mCdCpSzJ) contains
  them: one U+200E at the start of its title line and two U+200F mid-sentence. The other two contain
  none. The stored original must keep them; normalized text for display and search can strip them.
- **Heuristics that never matched were removed** to avoid untested fallbacks: `<h1>` caption text,
  JSON-LD, and clicking a "more" toggle. The desktop page shows the whole caption.

## Limits of this evidence

- **Three posts:** all public Hebrew Reels shared as `/p/` links, with captions up to 2,126 characters
  (Instagram's limit is 2,200). Not tested:
  - the `/reel/` link form;
  - photo-only and carousel posts (other tools report one caption per carousel, not per item);
  - private and age-restricted posts;
  - posts whose creator disabled embedding;
  - deleted posts (probably the same as the nonexistent one, but untested).
- **Three runs, one day, one network.** Repeated use may hit rate limits. Results may differ on VPN or
  data-center networks, in other regions (for example a cookie-consent dialog), or after Instagram
  changes its pages, which happened several times in 2026.
- **Logged-in access** was not tested and was not needed.
- **Inside the server** (milestone 5), not tested here. On Windows, `uvicorn --reload` uses an event
  loop that cannot start Playwright, which fails with an empty `NotImplementedError`. The tooling
  research reproduced this and verified two workarounds: a dedicated thread running its own Proactor
  loop, or a child process.

## Recommendation for the importer (milestone 5)

1. **Primary:** Playwright loads the logged-out post page and reads the post's own data. This is the
   approach the brief asked to investigate. It reads the current data, including co-authors, and
   what it reads is what a visitor sees. Captures took 3.4–6.5 s here, each starting a fresh
   browser. Windows needs the thread or process isolation above.
2. **Fallback:** an HTTP GET of the public embed view, reading `contextJSON` (about 1 s). Use it only
   when the post page fails, and record which source supplied the caption. It may lag behind edits,
   its data shape is legacy, and embed content is meant for embedding (see [Terms](#terms-of-use)).
   Whether to keep this fallback at all is your call in milestone 5.
3. **Last resort:** use the meta preview, always flagged "may be incomplete — compare with the post".
4. **Otherwise:** say "the post could not be read" with the reason (login required, unavailable, rate
   limited, timeout, caption not found). Keep the URL and offer *paste caption* and *upload
   screenshots* right there.
5. **Never:** log in automatically, reuse your browser's cookies, disguise the client, or retry in
   loops. At most one bounded retry, for timeouts only.

The outcome names in `backend/app/importers/instagram.py` already separate *the post was read*
(`caption_found`, `caption_incomplete`, `no_caption`) from *the post could not be read*
(`login_required`, `unavailable`, `rate_limited`, `caption_not_found`, `timeout`, `error`). "Read,
but no usable recipe in it" is decided later by AI extraction, not by the importer.

## Terms of use

- **Automated collection.** Instagram's [Terms of Use](https://help.instagram.com/581066165581870)
  restrict collecting information in automated ways without permission.
- **Embeds.** Meta's documentation for its official embed API says embed content is for embedding
  ([oEmbed docs](https://developers.facebook.com/docs/instagram-platform/oembed)). Extracting
  captions from the embed view arguably falls outside that, which is one reason it is only a
  fallback.
- **What this importer does.** It is limited to what you could do by hand: it fetches **one public
  post that you explicitly paste**, at human pace, and reads the content a visitor sees. There is no
  bulk collection, no login automation, and no evasion.
- **It can stop working at any time.** That is why pasting the caption and uploading screenshots
  stay first-class paths.

## In the app (milestone 5, 2026-10-26)

The importer now runs inside the backend (`retrieve_caption` in `backend/app/importers/instagram.py`,
`POST /api/imports/instagram`), following the recommendation above: the post page in a fresh
logged-out browser, the embed view once only when that gives no complete caption, a preview never
taken as complete, Instagram's own "unavailable", "no caption" and "wait" taken as final.

Checked again from this computer on 2026-10-26, 9 page loads in all, at human pace:

| What | Result |
|---|---|
| The probe, `browser-post` only, the three posts | 3 of 3 `caption_found`, byte-identical to the 2026-10-18 captions, 4.4–7.7 s |
| In the app (a `uvicorn --reload` server on Windows), the three posts | 3 of 3 read from the post page, byte-identical, 3.9–5.4 s; `DPbKEn-CnUt` also read twice more in the end-to-end test (6.8 s, 3.5 s) |
| The `/reel/` form of an address (`/reel/DPbKEn-CnUt/`), not tried in milestone 1 | read, identical |
| The nonexistent post `AAAAAAAAAAA` | `unavailable` after the post page alone (3.2 s); the embed view was not loaded |

The co-author of `DANUmOOIcRM` (alehonline) came through with its author. The embed fallback was not
needed in any live load; it is covered by offline tests only. Still untested live: photo and carousel
posts, private and age-restricted posts, posts with embedding disabled, and a real rate limit.

## Pictures and videos (2026-10-26)

The same post data lists the post's media: `media_type` 1 (image), 2 (video) or 8 (carousel, items in
`carousel_media`), each with `image_versions2.candidates` (several sizes, the largest first; some
without sizes) and, for a video, `video_versions` (no sizes; often one address listed three times) and
a poster in `image_versions2`. The embed view has the older shape (`display_url`, `display_resources`,
`is_video`, `video_url`, `edge_sidecar_to_children`). The files themselves are on Instagram's media
servers (`*.fbcdn.net`) and downloaded with a plain HTTP client, no cookies, at once: their addresses
expire.

Formats seen live in the post data: reels (`Cm1mCdCpSzJ`, `DPbKEn-CnUt`, `DANUmOOIcRM`: one video
with its poster), a mixed carousel (`CLJ5G9rDi1a`: video, image, video), a photo carousel
(`DQbcFZziKTW`: 14 images). A single-image post was not found among the posts available; it is tested
with fixtures of the same shape (`media_type` 1 at the top).

**Verified live through the page (2026-10-28)**, on a separate test database and media folder, in
Microsoft Edge, with the app's own code; five post reads in about 25 minutes, none blocked:

| Post | Format | What was checked | Result |
|---|---|---|---|
| `CLJ5G9rDi1a` | Mixed carousel | A new import: credit, media, cover, video playback | Credit "Shayna Gershovitz \| שיינא (@shaynzzz)" from the post's data; video, image, video saved in order (5 files with the posters, 5.3 MB); the draft in 23 s including the local model. The video plays only when asked, seeks (byte ranges), 720×900. |
| `DQbcFZziKTW` | Photo carousel (14 images) | Media for an existing recipe typed in by hand, with an edited credit and an upload as its cover | 14 images in 4.9 s; title, ingredients, steps, notes, categories, credit and status unchanged, no new recipe, the upload still the cover. Fetching again: "14 כבר היו במתכון", nothing added. A normal import of the same link still gets the duplicate warning. |
| `Cm1mCdCpSzJ` | Reel | A partial download, then a retry | With the test backend refusing videos over 300 KB (the real 150 MB limit, lowered for the check; the post and the download were real), the video was refused: the draft opened with the review point and the video's still, and was saved as a recipe; the viewer showed the still, "הסרטון עצמו לא נשמר במחשב הזה" and a link to the post. After a restart with the normal limits, "שליפת מדיה מהפוסט" saved the video (31.6 s, 720×1280), which then played. |

Also checked: a picture uploaded to a sample recipe without any link; choosing a video's still as the
cover; removing a picture (its file was deleted, as no other recipe used it); everything still there
after a page reload and after two backend restarts; a 390 px wide screen without sideways scrolling.

**Tested with fixtures only** (no live case): a single-image post; the embed view's media shape; an
image over 20 MB; a post over 400 MB or past 180 s; a refused or failing address for each item; a
file that is not what it claims (the type is read from its first bytes); more than 20 items; two
recipes sharing one file.

## Re-running the probe

From `backend/`:

```bash
uv run python -m scripts.probe_instagram                        # the three posts, at most 12 page loads
uv run python -m scripts.probe_instagram https://www.instagram.com/p/<code>/   # your own public post
uv run python -m scripts.probe_instagram --strategies browser-post,http-embed
uv run python -m scripts.probe_instagram --headed                # watch the browser window
uv run python -m scripts.probe_instagram --analyze <run-id>      # offline, e.g. 20261018-142944
```

Each run writes a new folder under `<data folder>/instagram-probe/` with `summary.md` and
`summary.json`. Runs pause 10 s between page loads, are capped at 10 URLs, and stop at the first
sign of rate limiting or a login wall. Running it again in a few weeks is a cheap way to notice
when Instagram changes.
