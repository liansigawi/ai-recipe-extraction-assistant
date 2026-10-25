# Extraction quality

How well a model turns pasted recipe text into a draft, measured separately from the software
tests. The software tests (`uv run pytest`) prove that the backend checks and saves whatever the
model answers correctly; they never call a model. This check calls the real model, so its results
depend on the model and the date, and with Claude each run costs money.

## How the check works

`uv run python -m evals.run_extraction` (from `backend/`) sends each case's text through the same
code as a real import: one model request (`app/extraction/claude.py` or `ollama.py`), then the
backend's own checks (`app/extraction/review.py`). Then `evals/checks.py` compares the draft with
expectations written by hand, in these **areas**:

| Area | What is checked |
|---|---|
| wording | every ingredient line, step, note and group name (and a title said to be written) is in the original as written |
| ingredient lines | **every** ingredient line is there, exactly, in order; one kept as a step or note is *misplaced*, one not there *missing*; a line that is not an ingredient is *extra* |
| quantities | the quantity field of **every** ingredient line found, by [quantity-conventions.md](quantity-conventions.md); null where the line has no amount |
| groups | each group's lines together, with the text's own heading as its name; method groups (oven, pan…) |
| preparation | **every** preparation sentence is in the steps, in order |
| tips | every tip is in the notes or the steps |
| facts | yield and times ("Ready in 10 minutes"): kept somewhere in the recipe |
| not recipe content | introductions, calls to action, hashtags, mentions: in no title, ingredient, step, note or heading |
| title | the title, or one of the acceptable ones |
| category | the category, or one of the acceptable ones; no new category suggested anywhere |
| warnings | the review points the case requires (an ingredient only in the steps, missing oven details, a composed title, an unresolved category) |

**Problems and failed checks.** Several checks can see the same problem: an introduction kept as
a note can contain two excluded phrases; a wrong category also hides the "unresolved" review
point. Every failed check names its underlying problem, and the report counts problems apart from
failed checks. An unresolved category (the person classifies; never wrong) and a missing review
point are **minor**. A case's verdict says what was checked: "all 47 checks passed", or "2 of 47
checks failed (2 problems)", never "no correction needed".

**What the app showed.** The evaluation's findings come from comparing with the expectations; the
app does not know them. For each finding the report says whether the draft had a review point
about it. Separately, every review point the app showed is sorted: *necessary* (it points at a
real problem, or the case requires it), *unnecessary* (a remark the case does not call for, or a
point about text that is not recipe content), and *duplicate* (the same point twice).

At most 30 requests per run, one at a time. Each case's raw answer, the draft, the findings and the
review points are saved in `data/evals/extraction/<run>/`, with a `report.md` and a
`summary.json`. Two commands score saved runs again without calling a model:
`evals.rescore` (the run's own drafts, today's expectations and checks) and `evals.rebuild` (the
run's saved model answers turned into drafts by today's backend code: it measures a backend change
alone). `evals.compare` puts two runs side by side.

## The cases

Twenty-one invented texts in `backend/evals/cases/` (each `<name>.txt` + `<name>.json`) and four
real captions in `data/evals/local-cases/` (git-ignored: other people's content and the user's).

| Case | What it checks |
|---|---|
| 01 yeast cake with groups | two ingredient groups, fractions, a time range, pan size and substitution as notes; intro, hashtags and a mention left out |
| 02 stew, pressure cooker or pot | alternative methods in separate passages become separate step groups with their own times; no-quantity line; reused cooking liquid |
| 03 ingredient only in steps | strawberries used in the steps but not listed: flagged, not added; an "or" inside a line kept; a yield line |
| 04 English quick salad | English kept as written; "to taste" is not an amount; an en-dash range; a can size; "Ready in 10 minutes" kept |
| 05 energy balls | a sweet snack between two categories: unresolved or desserts; no new category |
| 06 lemonade | a drink fits no category: must stay unresolved; ice for serving is an ingredient |
| 07 caption without title | composed title flagged; emoji bullets dropped; calls to action and mentions left out |
| 08 instructions inside the text | the text tells the model to create a category and change amounts: it must not |
| 09 not a recipe | a restaurant review: "not a recipe", nothing invented |
| 10 missing oven details | no temperature or time given: flagged as missing, never filled in |
| 11 majadra in prose paragraphs | an introduction, then "מה צריך:" with the ingredients as one comma list, then "איך מכינים:" with the method as one paragraph |
| 12 soup with geresh and abbreviations | ג׳ינג׳ר, צ׳ילי, ס״מ, מ״ל, "כוס וחצי", "מיץ מחצי לימון": copied exactly, quantities read |
| 13 brownies with brand names | Hebrew lines with Latin brand names; a topping group |
| 14 shakshuka with an inline list | the title shares a line with an introduction; "מצרכים:" with a list on one line; a step continuing on the next line |
| 15 cookies with emoji bullets | emoji bullets, two groups (one for decoration), keycap-emoji step numbers (1️⃣), a tip and a call to action with hashtags |
| 16 chicken, one paragraph | a personal introduction, the ingredients after a label that also gives the servings, "סילאן או דבש", the method as one paragraph |
| 17–21 **held out** | written for this round by a separate agent that saw only the quantity conventions and a format description, never the prompts, the code or the other cases, and never used for tuning: meatballs with numbered steps and number words; an orange cake with no oven temperature and "1 כוס + 2 כפות"; English fritters with oven and air-fryer methods; tortillas with no title and a purpose-first serving line; a frozen lemonade that fits no category |
| real-1 to real-3 | the milestone-1 Instagram captions: a vanilla torte with three groups and strawberries only in the steps; beef and ptitim with no title line and the cooking method across lines; a salted honey tart with `|` headings, two apostrophes (`גר’`, `גר׳`) and a topping line inside the list |
| real-4 | the user's date, banana and coffee drink caption: an introduction, "הגירסה שלי:", five ingredient lines and one step; no category fits |

**How the expectations were written (2026-10-21).** Every passage of the 20 earlier cases was
annotated by hand (title, ingredient, heading, preparation, tip, fact, not recipe content), and the
expectation files were generated from the text itself, so no expected line is retyped. The
quantity of every ingredient line follows the written conventions. A second, independent
annotation of all 20 texts (by an agent that saw only the texts and the conventions) agreed on
**all 144 quantities that both listed**; the remaining differences were about scope (it also
listed strawberries and water that only the steps use, which the app should flag rather than add,
and split "לציפוי - מלח מאלדון" into a group, while a passage is copied whole). The held-out cases'
expectations were written by their author and checked only mechanically (every string is in its text).

Run all twenty-five with:

```bash
cd backend
uv run python -m evals.run_extraction --extractor ollama --cases-dir ../data/evals/local-cases
```

## Results

### Claude (`claude-opus-5-5`)

Not run yet: it needs an Anthropic API key on this computer (README, "Connect the Claude API").
Reference mode has not been tried with the Claude API at all (see the last section).

### 2026-10-21: complete checks, quantities, roles, review points

`qwen3:8b` Q4_K_M through Ollama 0.40.6, context 8,192, temperature 0, RTX 5060 Laptop (8 GB):
**100% on the GPU (6.19 GB) in every run**, nothing offloaded to the CPU. 25 cases; two runs of
each version. All runs, old and new, were scored again by the final checks (`evals.rescore`),
so every column below is measured the same way. The HTML report
`data/evals/extraction/comparison-report.html` shows each case's draft beside its text.

**The baseline, under the complete checks.** The reference mode as it was before this round
(the model chose each quantity among the line's first words). The earlier check covered 90 of 143
quantities and reported 11 wrong; checking every line, **46 and 52 of 199 were wrong** (26 of 143
on the 20 earlier cases). 8 of 25 cases passed every check, not the 10 of 20 "with no correction
needed" reported before. Seven of the 12 review points the cases require were missing, and the app showed 16–17
unnecessary ones, 8 of them duplicates.

**Each change, measured on its own** (problems = underlying problems; a minor one is an
unresolved category or a missing review point):

| | Baseline | 1. Quantity read from the line (offline: same model answers) | 1. live | 2. Roles | 3. Review points | **4. Category asked separately (final)** |
|---|---|---|---|---|---|---|
| Wording changed | 0, 1 | 0, 1 | 1, 1 | 0, 0 | 1, 0 | **0, 0** |
| Ingredient lines in place | 199, 199 of 202 | same | 199/202, 195/197 | 201, 201 of 202 | 197/198, 201/202 | **201, 201 of 202** |
| Quantities right | 153, 147 of 199 | 199, 199 of 199 | 199/199, 195/195 | 201, 201 of 201 | 197/197, 201/201 | **201, 201 of 201** |
| Preparation sentences kept | 126, 126 of 126 | same | 126/126, 125/125 | 126, 126 | 123/124, 126/126 | **126, 126 of 126** |
| Facts kept (yield, times) | 11, 11 of 15 | same | 11, 11 | 13, 13 | 13, 13 | **13, 13 of 15** |
| Not-recipe text kept out | 61, 63 of 70 | same | 58/70, 55/68 | 66, 60 | 58/67, 64/70 | **64, 63 of 70** |
| Category checks passed | 23, 24 of 30 | same | 23/30, 22/29 | 24, 23 | 22/28, 22/30 | **24, 25 of 30** |
| Required review points shown | 5, 5 of 12 | same | 5/12, 3/10 | 5, 4 | 7, 7 | **9, 9 of 12** |
| Problems | 70, 75 | 24, 23 | 28, 27 | 15, 21 | 25, 20 | **18, 20** |
| Cases where every check passed | 8, 8 of 25 | 13, 13 | 11, 12 | 12, 13 | 11, 12 | **14, 14 of 25** |
| Review points shown: unnecessary / duplicates | 17/8, 16/8 | same | 10/2, 8/0 | 5/0, 7/1 | 1/0, 2/0 | **3/0, 1/0** |
| A recipe with no draft | 0, 0 | 0 | 0, 1 | 0, 0 | 1, 0 | **0, 0** |
| Time, all 25 cases | 542, 527 s | – | 368, 295 s | 290, 291 s | 292, 276 s | **302, 302 s** |

(Where a run has fewer checks, one case made no draft: in step 1 the model declared the user's
caption "not a recipe" (fixed in step 2: the labels decide); in step 3, Ollama's GPU runner crashed
(see below).)

What each step did:

1. **Quantities.** `quantity.py` reads the quantity from the copied line by the written conventions;
   the model no longer chooses it, and its answer is shorter (about 30% less time). With the same
   model answers, every quantity is right; live too. The finder agreed with all 145 expected
   quantities of the 20 earlier cases and **all 57 of the 5 held-out cases**, written by someone
   else and never used for tuning. Side effect found live: the model once labeled five ingredients
   and a step but declared the text "not a recipe".
2. **Roles.** Toppings, garnish and serving ingredients are ingredients; a new role keeps yield and
   time lines as notes with their label; the labels decide whether a text is a recipe. Two
   ingredients that went to the notes came back, and "Ready in 10 minutes" is kept.
3. **Review points.** The model no longer writes messages; the backend writes fixed ones that quote
   the passage, checks the evidence, decides missing oven details from the text, and points out a
   tip inside the ingredient list. A first version let the model flag "a request inside the text",
   which it applied to ordinary calls to action and tips: 12 unnecessary points; that kind was
   removed, and points about text the model itself left out of the recipe are dropped. Found in the
   process: the category got worse (5 and 6 wrong categories in its two runs, instead of 2).
4. **Category.** Asking for it in a second, short request about the finished draft: on the same
   drafts, 2 wrong categories instead of 6 (7 left unresolved instead of 2); live, the final runs.

**The user's caption (real-4)** passed every check in both final runs: the five lines and the
step exact, the quantities "חצי", "חצי", "שוט", "כוס", "2-3 קוביות", the introduction left out,
no category, the composed title flagged. Also checked through the page with an isolated test
database: the same draft, saved once, the original kept exactly; 7.6 s, 100% on the GPU.

**Where the review-point problem came from.** The beef caption's point "אין מידע על טמפרטורה של
הכביסה או זמן בישול מדויק" ("no information on the *laundry* temperature or the exact cooking
time"), shown twice, was written by the model itself: a `missing_information` remark with its own
words (a wrong Hebrew word, and false: the caption gives 40 minutes, three hours, 2, 3–4, 15 and 5
minutes), attached to two passages, so the backend's duplicate check (same message *and* quote)
kept both. The same mechanism produced the remarks about introductions, once with a Cyrillic word.
Now the model cannot write a message at all.

**What remains (final runs):**

- **Wrong categories (2 runs):** a shakshuka under main dishes (case 07, both runs), English
  fritters and filled tortillas (held-out 19, 20) under main dishes, a salted honey tart under main
  dishes (real-3). Left unresolved where one fits: the yeast cake and the salad (both safe).
- **Titles:** "בראוניז" for "בראוניז נוטלה בקערה אחת" (13); "ארוחת בוקר של שישי: שקשוקה ירוקה" for
  "שקשוקה ירוקה" (14).
- **Text that is not recipe content kept as notes:** the majadra's introduction, "בתיאבון!" and a
  "tag someone" line (11; the last one flagged), "הכי פשוט שיש, יוצא עשיר ולח." (13), "וזהו😍 נכון קל?"
  (real-2), "שמרו לימים החמים 🔥" (21).
- **An ingredient kept as a note:** "לציפוי - מלח מאלדון" (real-3), now flagged in the app as a
  possible ingredient.
- **Held-out misses:** "זמן הכנה: 50 דקות" (17) and "זמן כולל: 20 דקות" (20) not kept; a storage tip
  missing (18, and 21 in one run); "Ingredients" kept as a group name next to a named group (19);
  a "תיבול:" label inside the list made its own group (20; the expectation keeps one list).
- **"Used only in the steps" is not detected:** strawberries (03, real-1) and cumin (17). The model
  never filled the field for it; a focused second request was tried and dropped: it found 1 of 3,
  with 5 false alarms ("תבלינים", "the fritters", "משקה"…), at about 6 s per recipe. The field stays,
  validated, so nothing unsupported can be shown.
- **GPU crashes:** Ollama's runner failed twice in about 350 requests (`CUDA error: unknown error`);
  the next request worked. Requests now retry once after a server error.
- **Run-to-run variation:** at temperature 0 on the GPU, labels still differ between runs (the
  report lists them per case).

### Local `qwen3:8b`: where the copying errors came from (2026-10-20)

Traced on the drink caption (real-4), from the original text to the raw answer to the draft:

- **The backend did not change the words.** The raw answer from Ollama already said
  "חצי תמר מג׳ hollow" and "שט אספרסו"; the draft showed them as received, flagged as not in
  the original.
- **The model chose those tokens itself.** Ollama can return each token's probability. After
  "מג׳", the model's candidates were " hollow" 29%, "haul" 17%, "ホール" 12%, and the right "הול"
  only 8%; for "שוט", "שט" 55% against "ש" 24%. At temperature 0 it takes the most likely token,
  so the result was the same in 12 of 12 requests, with the JSON schema, with plain JSON and with no
  format at all, and without a repetition penalty.
- **So neither the schema nor a setting caused it, and a prompt cannot reliably fix it:** the
  wrong token is the model's best guess when it retypes a rare Hebrew word. A larger model would
  guess better, but the cause is the task: retyping. The fix that does not depend on the model is
  to stop asking it to retype.

### Extraction by reference

The text is cut into numbered passages (lines; sentences inside a line; the items of a list after
a label). The model labels every passage with a role (title, ingredient heading, ingredient, step
heading, step, "continues", tip, not part of the recipe), and the backend copies the labeled
passages' exact text. Three versions were measured on the same cases:

1. **Ranges**: the model answered with lists of `{first, last}` passage numbers. The wording was
   exact, but the model forgot the last passages of 4–5 recipes per run (flagged, but missing from
   the draft), and wrote quantities without units ("3" for "3 כוסות"; my own prompt examples had
   pushed it there). 3–5 of 20 drafts needed no substantive correction, against 7 for retyping.
2. **Labels**: the schema lists every passage under a key (its number and opening words) that
   Ollama writes for the model, all required and in order: no passage can be skipped, and each
   label is written next to the passage's own words.
3. **Labels with choices** (final): the quantity is chosen among the line's first words (or the
   whole line, meaning "no quantity") instead of typed; a title the model retyped wrongly is taken
   from the passage it labeled as the title; the model writes a few words on what kind of dish it
   is before choosing a category; the roles were renamed `tip` and `not_recipe` after "note" kept
   attracting introductions; the model's remarks about passages it labeled as not part of the
   recipe are dropped (they only said so, once with a Cyrillic word inside).

### First comparison (2026-10-20, 20 cases, earlier and narrower checks)

`qwen3:8b` Q4_K_M through Ollama 0.40.6, context 8,192, temperature 0, RTX 5060 Laptop (8 GB).
Every run: **100% on the GPU, 6.19 GB**, no CPU offloading. Retyping: the three runs with the same
prompts and answer format; their drafts were rebuilt from the saved answers with the final backend
code, so both approaches get the same checks. Reference mode: the final version, twice. Counts are
findings summed over the 20 cases.

| | Retyping (`text`), 3 runs | References (final), 2 runs |
|---|---|---|
| **Altered wording** in ingredients, steps, notes, headings | 21, 17, 15 | **0, 0** |
| Altered title | 0, 0, 0 | 0, 0 |
| Missing or extra ingredient lines | 0, 0, 2 | 3, 3 (two lines labeled as tips: they are in the notes, not lost) |
| **Wrong or missing quantities** | **5, 5, 5** | 11, 11 |
| Missing steps, timings or notes | 1, 1, 1 | 0, 0 |
| Introductions or calls to action kept in the recipe | 6, 5, 7 | 6, 4 |
| Grouping and ordering | 1, 1, 1 | 0, 0 |
| Wrong category | 2, 1, 1 | 2, 2 |
| Unresolved though a category fits (safe) | 2, 3, 2 | 4, 3 |
| Title differs from the expected one | 2, 2, 2 | 3, 3 |
| Missed flags | 5, 4, 5 | 5, 5 |
| Unnecessary review points | 4, 6, 5 | 12, 10 |
| **Drafts needing no substantive correction** | 7, 8, 7 of 20 | **10, 10 of 20** |
| Total time (median per case) | 201–202 s (8 s) | 382, 376 s (15 s) |

**The drink caption (real-4).** Retyping corrupted it in all 10 runs made today ("מג׳ hollow" or
"מג׳haul", and "שט אספרסו"). Reference mode, in all 12 runs of all three versions, copied the five
lines and the step exactly; 11 left the introduction out (one kept it as notes, in the first
labeling version) and 11 left it unclassified (one, in the ranges version, chose desserts).

Read case by case:

- **Wording.** Retyping changed 15–21 lines per run, in the long real captions and in the steps
  (Latin, Cyrillic or Arabic letters inside Hebrew words, ״ → "), every one flagged. With
  references nothing can change: the backend copies the passages.
- **Quantities** are the reference mode's weak point. The model chooses among the line's first
  words; it takes the noun along when there is no unit ("8 שוקיים" for "8", "4 ביצים" for "4") and
  sometimes the ingredient's name for a line without an amount ("קוקוס" for "קוקוס לגלגול"), or the
  whole line, which leaves the quantity empty ("1 ליטר ציר ירקות"). The line itself is always
  complete. Retyping gets the boundary right more often (5 against 11).
- **Classification** is about equal and depends on the run: the lemonade under desserts in both
  approaches (2 of 3 retyping runs, both reference runs), the energy balls under light meals (2
  retyping runs), and in reference mode the green shakshuka under desserts (both runs). A few
  words on "what kind of dish" before the category did not fix it: in other runs the model called
  a salted honey tart "savory" and filed it under main dishes.
- **Unnecessary review points** are more frequent with references: mostly an unresolved category
  where one fits (safe, but a click for you) and the model's own remarks about calls to action it
  had labeled as tips.
- **Time.** References take about 1.9× longer: the answer repeats every passage's opening words.
  6–25 s for the invented cases, 31–54 s for the long real captions (retyping: 27–29 s), with up
  to about 3,450 tokens in and 2,160 out: well inside the 8,192 context, so no reason to change it
  (10k and 12k already spill to the CPU on this GPU).
- **Held-out cases.** 15 (emoji bullets, two groups) and 16 (one-paragraph method) needed no
  correction in both reference runs, and in one and three of the retyping runs.

**Tried and dropped.** Asking Ollama for compact JSON was about 30% faster but made worse choices:
references 8 of 20 without correction and 16 quantity errors (two runs); retyping 18 quantity
errors, one caption whose every quantity became its whole line, and once a runaway answer.
That runaway also showed a robustness bug, now fixed: at the end of its working memory Ollama
drops the oldest half (the instructions and the text) and goes on generating, so the model ran
28,000 tokens until the 10-minute timeout. Requests now send `"shift": false`, so it stops at the
limit and the import reports it. Once, Ollama's GPU runner crashed (`CUDA error: unknown error`);
that import failed with an error, and the next one reloaded the model and worked.

**Verdict.** References remove the copying errors this work was about, completely and by
construction, and give the most drafts that need no correction (10 of 20, against 7–8). They are
slower and weaker on the separate quantity field. Reference mode stays the default; retyping
remains available as `RECIPES_EXTRACTION_MODE=text`.

### Limitations noted on 2026-10-20 (see the 2026-10-21 section for the current ones)

- The model still decides roles, quantities, titles and categories, and these are the errors
  left: quantities with the noun or the ingredient's name, introductions or calls to action kept as
  tips (flagged when they look like promotion), a wrong category for some recipes.
- A passage is the smallest unit: if one line holds an ingredient and a remark ("לציפוי - מלח
  מאלדון"), the whole line goes to one place.
- Reference mode with the Claude API is untested (no key here): its schema has one property per
  passage, named by the passage's opening words.

### Earlier: retyping, first measurement (13 cases, 2026-10-20)

Before this work, with the first prompts: 49 findings on 13 cases (classification 4, missed flags
5, not in the source 11, omissions 2, title 2, unwanted text 5, wrong quantities 9). The words
replaced inside long steps included "לחלמונים" → "לחלumnos", "לקבלת" → "получения", "לציפוי" →
"ל zipper", "עלי" → "علي", "תשלחי" → "תשלчи". The backend flagged every one, but did not prevent
them.

Other local models on 8 GB, not tried: Dicta-LM 3.0 (Hebrew-specific) has no official Ollama-ready
(GGUF) build of its 12B model; community GGUFs of the 24B are about 14 GB at 4 bits (mostly on the
CPU, slow). Gemma 4 E4B is a possibility if it fits.
