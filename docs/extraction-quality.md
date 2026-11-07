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
| facts | yield and times ("Ready in 10 minutes"): kept somewhere in the recipe; kept but split over two adjacent notes is *split* (minor), apart from *missing*; servings filled when the text gives no yield fail |
| not recipe content | introductions, calls to action, hashtags, mentions: in no title, ingredient, step, note or heading |
| title | the title, or one of the acceptable ones |
| category | the category, or one of the acceptable ones; no new category suggested anywhere |
| source gaps | an ingredient the source recipe's steps use but its own list leaves out: the draft must not add it, and the app should point it out. A problem of the source, reported apart from extraction mistakes |
| warnings | the review points the case requires (missing oven details, a composed title, an unresolved category) |
| imports | apart from the areas above: was a recipe imported, was a text that is not a recipe refused. A refused recipe has no lines to check, so it would vanish from the per-area counts; it is counted here, and its case fails |

**Problems and failed checks.** Several checks can see the same problem: an introduction kept as
a note can contain two excluded phrases; a wrong category also hides the "unresolved" review
point. Every failed check names its underlying problem, and the report counts problems apart from
failed checks. **Minor** findings are failed checks where the draft is not wrong: an unresolved
category (the person classifies), a missing review point, a source gap not pointed out, a fact or
tip kept but split over adjacent notes. They are reported apart, never hidden: a case's verdict
says "all 47 checks passed" only when every applicable check passed, minor ones and required
review points included; otherwise "3 of 47 checks failed (2 problems, 1 minor)".

**What the app showed.** The evaluation's findings come from comparing with the expectations; the
app does not know them. For each finding the report says whether the draft had a review point
about it. Separately, every review point the app showed is sorted: *necessary* (it points at a
real problem, or the case requires it), *unnecessary* (a remark the case does not call for, or a
point about text that is not recipe content), and *duplicate* (the same point twice).

At most 40 cases per run, one at a time (with the local model a recipe takes two requests: the labels, then the category). Each case's raw answer, the draft, the findings and the
review points are saved in `data/evals/extraction/<run>/`, with a `report.md` and a
`summary.json`. Two commands score saved runs again without calling a model:
`evals.rescore` (the run's own drafts, today's expectations and checks) and `evals.rebuild` (the
run's saved model answers turned into drafts by today's backend code: it measures a backend change
alone). `evals.compare` puts two runs side by side.

## The cases

Sixty-one invented texts in `backend/evals/cases/` (each `<name>.txt` + `<name>.json`) and five
real captions in `data/evals/local-cases/` (git-ignored: other people's content and the user's).
Since 2026-11-03 (migration 0014) a dessert case expects a type (`subcategory`) and, apart from it, a
healthy style (`healthy`, or `healthy_one_of`), each checked on its own; the thirteen cases that expected
"קינוחים רגילים" or "קינוחים בריאים" expect the same choice as a healthy style.

| Case | What it checks |
|---|---|
| 01 yeast cake with groups | two ingredient groups, fractions, a time range, pan size and substitution as notes; intro, hashtags and a mention left out |
| 02 stew, pressure cooker or pot | alternative methods in separate passages become separate step groups with their own times; no-quantity line; reused cooking liquid |
| 03 ingredient only in steps | strawberries used in the steps but not listed (a source gap): pointed out, not added; an "or" inside a line kept; a yield line |
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
| 17–21 | held out in the 2026-10-21 round (their failures were examined in the 2026-10-25 round, so they are no longer held out): written by a separate agent that saw only the quantity conventions and a format description, never the prompts, the code or the other cases, and never used for tuning: meatballs with numbered steps and number words; an orange cake with no oven temperature and "1 כוס + 2 כפות"; English fritters with oven and air-fryer methods; tortillas with no title and a purpose-first serving line; a frozen lemonade that fits no category |
| real-1 to real-3 | the milestone-1 Instagram captions: a vanilla torte with three groups and strawberries only in the steps; beef and ptitim with no title line and the cooking method across lines; a salted honey tart with `|` headings, two apostrophes (`גר’`, `גר׳`) and a topping line inside the list |
| real-4 | the user's date, banana and coffee drink caption: an introduction, "הגירסה שלי:", five ingredient lines and one step; no category fits |
| 22–26 | fresh in the morning round of 2026-10-25 (written by a separate agent, kept unread until measured), then used for fixes: a chicken and rice pot, salted caramel brownies, avocado and egg toast, a roasted tomato soup, brined pickles |
| 27–33 **fresh** | written for the afternoon round of 2026-10-25 by a separate agent with the same restrictions, kept unread until measured: a watermelon drink with a personal introduction, ricotta-stuffed shells, harissa chicken (English), a no-bake cheesecake with no title line, a fish chraime, and two texts that are **not recipes** (a market haul whose lines start with amounts, a workshop announcement) |

**How the expectations were written (2026-10-21).** Every passage of the 20 earlier cases was
annotated by hand (title, ingredient, heading, preparation, tip, fact, not recipe content), and the
expectation files were generated from the text itself, so no expected line is retyped. The
quantity of every ingredient line follows the written conventions. A second, independent
annotation of all 20 texts (by an agent that saw only the texts and the conventions) agreed on
**all 144 quantities that both listed**; the remaining differences were about scope (it also
listed strawberries and water that only the steps use, which the app should flag rather than add,
and split "לציפוי - מלח מאלדון" into a group, while a passage is copied whole). The held-out cases'
expectations were written by their author and checked only mechanically (every string is in its text).

**Expected categories (2026-10-25, evening)** follow the person's reorganized categories:
"קינוחים" sweet desserts, dairy desserts included; "ארוחות בשריות" (formerly "בישולים") meat and
poultry meals; "ארוחות קלילות" savory dairy or egg meals (shakshuka 07 and 14 and the spinach-cheese
pie 10 now belong there); "משקאות", added by the person, drinks (the lemonades 06, 21, the watermelon
drink 27 and the coffee drink real-4). Fish, vegetable, legume and other dishes without a clear fit
stay unclassified (11, 26, 31; the soups 12 and 25 until 2026-11-01). A savory dish with cheese, yogurt
or egg as one part (fritters with a yogurt sauce 19, avocado toast with eggs 24; the feta salad 04 until
2026-11-01) accepts "ארוחות קלילות" or
unclassified. Case 06 used to check that a drink stays unresolved with no "משקאות" suggested; now
that the person added that category it expects it, and cases 05, 08, 24 and 25 still check that no
new category is suggested.

**Salads, soups and sides (2026-11-01).** The person added "סלטים", "מרקים" and "תוספות" (ids 7, 8, 9).
What the dish is decides over its main ingredient, so the feta salad 04 now expects salads and the soups
12 and 25 expect soups; a side is judged by its role. Cases 38–45 were written for this before the first
run and not used for tuning (a chicken soup, a goat-cheese salad, a chicken salad served as a meal, a
goulash soup, roasted potatoes, rice with vermicelli and green beans served alongside a main, and lentil
patties that are the meal itself, which fit none). Cases 46–49 were written while the descriptions were
still being compared, and used only to check the chosen ones (a tuna salad, a split-pea soup, ptitim
served beside schnitzel, egg fried rice as the meal itself).

**Spreads, dips and sauces; fresh cases (2026-11-01, later).** The person added "ממרחים, מטבלים ורטבים"
(id 10). Cases 50–61 were written before the classification change below was measured and never used to
tune anything: a herb butter, a pesto, hummus and a yogurt dip (the new category); pasta in a tomato-cream
sauce (a whole dish with a sauce: not a sauce); a French onion soup with cheese and a steak salad (soups
and salads with dairy or meat); quinoa with roasted vegetables served beside fish, against a quinoa bowl
with chicken that is the meal (a side against a complete meal); a baked sea bream, a sourdough bread and
seed crackers (no category fits).

A run takes at most 40 cases, so run them in parts, choosing cases with `--case` (repeatable):

```bash
cd backend
uv run python -m evals.run_extraction --extractor ollama --case 38-chicken-soup-noodles --case 39-goat-cheese-pear-salad
```

## Results

### Claude (`claude-opus-5-5`)

Not run yet: it needs an Anthropic API key on this computer (README, "Connect the Claude API").
Reference mode has not been tried with the Claude API at all (see the last section).

### 2026-11-07 (later): two replacements for the featured examples

The latte (17) and the savory pancakes (14), both filed as desserts above, were replaced on the comparison pages
by two savory recipes the classifier had right in both runs of the measurement of 2026-11-05, whose saved recipes
match their originals line for line. No website recipe qualified (51 and 55 were classified wrongly in that
measurement). Each was imported once through the Instagram import, its caption reader replaying what the original
import read and every download refused (16:51-16:52 UTC, qwen3:8b, temperature 0, code 8ab50fb), the first
completed run of each (`data/evals/extraction/20261107-replacements/`). Two curated recipes: not an accuracy
estimate.

| Recipe | The model's category · type | Expected | Points raised | Review changed |
|---|---|---|---|---|
| 36 חלומי קריספי פסטה | ארוחות קלילות | the same | 1 (no pictures found, the system's) | nothing |
| 38 סלט ענבים וירוקים | סלטים | the same | 1 (no pictures found, the system's) | nothing |

- **The point on pictures** came from the replay, which gave the import no media; it was marked done.
- **Extraction**: every ingredient line, quantity, step and note as the original has it; the group "למרינדה"
  (36) and the two remarks marked "*" (38) kept; the sponsor line, introductions, credit and hashtags left out.

### 2026-11-07: the five featured examples imported again, with the adopted classifier

The recipes of the five comparison pages, each imported once more from its preserved original on its own
copy of the notebook (11:51-11:53 UTC, qwen3:8b, temperature 0, code 75bfd06), the first completed run of
each, and reviewed while preparing the demonstrations (docs/public-notebook.md). Five curated recipes: not
an accuracy estimate.

| Recipe | The model's category · type | Expected | Points raised | Review changed |
|---|---|---|---|---|
| 12 טורט וניל | קינוחים · טארטים ופאי | קינוחים · עוגות | 1 (strawberries, the system's) | the type; the strawberries added |
| 15 עוגת קפה ושוקולד | קינוחים · עוגות | the same | none | a remark put back into its step |
| 17 בננה אייס לאטה | קינוחים · גלידות וקינוחים קפואים | משקאות | none | the category |
| 14 פנקייק מלוח | קינוחים · מאפים מתוקים | ארוחות קלילות | 1 (a note on the cheese, the system's) | the category; the yield line restored |
| 29 סופגניות קרם ברולה | קינוחים · מאפים מתוקים | the same | 2 (title, separate recipe, the system's) | nothing |

- **Categories**: 2 of 5 fully right (15, 29), the type wrong on one (12), the main category wrong on two
  (14 and 17, both filed as desserts again). Recipe 29, a meat meal in both runs before the classifier
  changed, is right; the others answered as on 2026-11-05.
- **The model's own points**: five, all on recipe 29, all "unclear or" on passages without "או", all left
  out by the rule.
- **Extraction**: the remark of 15 and the yield line of 14, labeled a tip and not part of the recipe,
  needed review; every other line was copied as the original has it.

### 2026-11-05 (evening): classification without the dish description, one candidate

Question: does the free-text "dish" description the category request asks for first (sweet or savory, what it
is, what it is mainly made of) cause wrong categories, or only accompany them? **One candidate**, frozen before
any run with the cases, the expected answers and the adoption criteria
(`data/evals/extraction/20261105-no-dish-description/`: `build_cases.py`, `requests.json`, `criteria.md`): the
production request without that description, its instruction ("First say in a few words what kind of dish it
is (...), then classify.") and its `dish` field. The same categories, the same rules, the same answer
otherwise (`fit`, the ids, ambiguous and no fit); the healthy style is left undecided by both. Each case's user
message was built once by the production code and sent byte for byte by both; both through the production
request (qwen3:8b, temperature 0, 8,192 tokens), two rounds, alternating; every answer kept, none rerun.

119 cases: the evaluation cases that are recipes (01-61, their drafts from the 2026-11-01 collection), the
person's 43 saved recipes with an original (12, 14, 15, 17 and 29 as today's production drafts), and the dessert
inventions of 2026-11-03 and 2026-11-04. **Held out** (no classification work used them): 24 cases, the seven
saved recipes never in an experiment (36, 37, 39, 49, 51, 53, 56) and the 17 inventions that were each run once
as a final check. Expected answers: the cases' own, the saved categories checked against the descriptions (five
read otherwise or not scored: 10, 24, 47, 49, 51), the inventions' frozen ones.

| 119 cases (each run gave the same totals) | Request as it was | Candidate |
|---|---|---|
| main category right | 90 | 98 |
| dessert type right, 55 desserts | 38 | 43 |
| fully right | 74 | 86 |
| wrong "clear" answers | 45 | 32 |
| unresolved (on the 103 straightforward cases) | 1 (0) | 1 (1) |
| held out, 24: fully right / main category right | 16 / 19 | 17 / 20 |
| cases whose two runs differ | 1 | 0 |
| one request: mean (median); output tokens | 1.43 s (1.37); 57 | 1.06 s (1.03); 40 |

- **By case** (recipe N: the notebook's; case N: the evaluation's): 17 better in both runs, 5 worse (a
  two-sided sign test on these: p = 0.017). Better: the doughnuts (recipe 29) no longer a meat meal; the flavored
  butters (recipe 26, case 50) and the hummus (case 52) no longer desserts; the tortillas (case 20), the chicken
  quinoa bowl (case 58), the savory cottage pie (2026-11-03's) and the halloumi pasta (recipe 36, held out) no
  longer desserts; three sides (cases 43, 44, 57); six dessert types (cases 03 and 18, recipes 13, 35 and 42, the
  held-out muffins h05). Worse: the harissa chicken (case 29) left unresolved, the cottage fritters (case 19) a
  dessert instead of unresolved, the egg fried rice (case 49) a side, two cake types (recipe 55, and the held-out
  crumb-base cheesecake h01).
- **Unchanged**: the latte (recipe 17) and the sahlab (recipe 50) are still desserts, the savory pancakes
  (recipe 14) still "מאפים מתוקים", the vanilla torte (recipe 12) still a tart. No dish that fits nothing was left unclassified by either.
- **The adoption criteria, all met**: fully right +12 (at least +6, and each candidate run above each run of the
  request as it was), held out not lower (+1), main category not lower (+8; held out +1), at most two more straightforward
  recipes unresolved (+1).

Limits: one model at temperature 0, whose two runs differed in one case, so the comparison is one paired measure
on 119 cases rather than two; a small held-out set (24, 17 of them desserts, no drink), where the gain is one case;
95 cases had shaped the request as it was (which, if anything, favors it); most saved recipes are reviewed
recipes, cleaner than drafts; the collection is not a sample of future imports. Measured with the local model
only. **Adopted for the local model** on 2026-11-05, exactly this request (docs/architecture.md,
2026-11-05 (9)); the Claude API keeps the description, as it was not measured without it. These figures describe
this collection, measured once: they are not an accuracy to expect of future imports, and the errors above remain.

### 2026-11-05 (later): the featured examples' classification, measured

The four recipes with a comparison page in the public copy, each classified by the current pipeline. A
curated set of four, chosen for the pages: **not an estimate of overall accuracy.**
- **Expected answers first**: written from each source and the category descriptions before any run
  (`data/evals/extraction/20261105-featured-classification/expected.md`, 14:57 UTC); the saved category was a
  reference to check, and agreed with them in all four.
- **Runs**: one fresh import of each preserved original on its own copy of the notebook (2026-11-05
  14:57-14:59 UTC; qwen3:8b through Ollama, references mode, temperature 0, 8,192 tokens; code 129d174 with
  that day's uncommitted changes, none of them to the prompts or the classification), its classification
  request and raw answer recorded, then that request sent again unchanged. Nothing tuned, no paid API.
  Recipe 17 was not rerun: its result is the demonstration recorded at 13:18 UTC.
- **The healthy style is not counted**: the model never sets it.

| Recipe | Expected | Saved | Shown before as the model's | This run, 1st / 2nd answer | Verdict |
|---|---|---|---|---|---|
| 15 עוגת קפה ושוקולד | קינוחים · עוגות | the same | nothing (no draft kept) | קינוחים · עוגות / the same | correct |
| 12 טורט וניל | קינוחים · עוגות | the same | קינוחים · טארטים ופאי (demonstration, 08:31 UTC) | קינוחים · טארטים ופאי / the same | type wrong |
| 14 פנקייק מלוח | ארוחות קלילות | the same | קינוחים (import draft, 2026-10-28) | קינוחים · מאפים מתוקים / the same | category wrong |
| 17 בננה אייס לאטה | משקאות | the same | קינוחים · קינוחי כוסות ומוסים (demonstration, 13:18 UTC) | (one answer) the same | category wrong |

- **Main category**: right for 2 of 4 (15, 12); wrong for 14 and 17, both filed as desserts. **Type**: right
  for 1 of the 2 desserts (12's layered torte became a tart); 14 also got a dessert type, being no dessert.
  Fully right: 1 of 4.
- **Consistency**: each request sent twice got the same answer twice (3 of 3). The same input is answered
  the same way; a different extraction of the same text can still change the answer (recipe 29 above).
- **12 against its demonstration**: the new draft equals the demonstration's of 08:31 UTC in every part,
  its category and type included.
- **The dish line**: the description the model writes before the category was wrong whenever the category
  was: 14 "מאפה מתוק או חם" for savory pancakes, 17 "קינוח מתוק עם ביצים וקמח" for an iced coffee with
  neither; 12's "עוגה עם שוקולד ותותים" names a cake (yet the type chosen is a tart) and chocolate the recipe
  does not have. Every classification request held only the draft's title, ingredients and steps, as copied.
- **14 then and now**: its import of 2026-10-28 also suggested "קינוחים" (with "קינוחים רגילים", the healthy
  style's old form; dessert types did not exist yet).

### 2026-11-05: the "unclear or" point, measured where it came from

Recipe 29's public comparison showed five "חלופה לא ברורה" points on passages without an "או". The local
model's own answer named those passages (recorded in a fresh run of the preserved caption, qwen3:8b,
temperature 0, code 129d174); the notebook quoted exactly the passages named. In the evaluation's stored
runs the model made 13 such claims, none on a passage with "או" or "or". The point is now shown only where
the passage has one (docs/architecture.md, 2026-11-05 (5)); no case in the evaluation requires it.

Repeated runs of the same caption at temperature 0 did not return the same answer: a third run chose the
other title and pointed its "או" claims at other passages, all of them filtered out. The category request,
which reads the finished draft, answered "savory" and "ארוחות בשריות" in both runs whose draft included the
caption's dough lines, and "מאפים מתוקים" in the run before they were kept.

**That category, inspected.** The classification requests were rebuilt from the recorded labeling answers
with the app's own `make_draft` and `build_classification_request` (run 1's at 129d174, before the dough
lines were kept), and each was sent once more through the production request:
- the recipe in the request is the draft's title, its 8 ingredient lines and its steps, all copied from the
  caption: custard, caramel and doughnuts, nothing savory and no meat;
- the categories are the notebook's, with their descriptions; "מאפים מתוקים" (16, under "קינוחים", 1)
  names סופגניות, and "ארוחות בשריות" (2) asks for meat or poultry as the main ingredient;
- the answer schema allows exactly the existing ids (categories 1-10, subcategories 11-16);
- the two requests differ by one line, the step "מכינים בצק סופגניות לפי המתכון לבצק סופגניות קלאסי שלי
  מהבלוג. עושים הכל לפי ההוראות כולל הטיגון.";
- with it, the raw answer was `"dish": "savory, cream-filled pastry"`, `fit: clear`, `category_id: 2` (3 of
  3 answers: runs 2 and 3, and the resend); without it, `category_id: 1`, `subcategory_id: 16` (2 of 2);
- the answer is parsed and mapped as written: id 2 is "ארוחות בשריות".

No implementation defect: the input, the categories and the mapping are right; the local model's answer is
wrong. Not tuned (no new wording was tried); recorded as a limitation (docs/architecture.md, "The local
model still files some dishes in the wrong category"). The runs, the rebuilt requests and the raw answers are kept in
`data/evals/extraction/20261105-recipe-29/`.

### 2026-11-05: recipe 17's caption imported again

Recipe 17 ("בננה אייס לאטה", imported 2026-11-01 with qwen3:8b) has no kept draft: it was saved 21 seconds
after its import, and the first backup after that is from 12:38 UTC. No other database, backup or
evaluation folder holds a draft of that import (the classification-context evaluation's "recipe-17" is the
saved recipe). Its preserved caption (real-4, on which retyping once turned "מג׳הול" into "מג׳ hollow") was
imported once more on a copy of the notebook (2026-11-05 13:18 UTC, qwen3:8b, references, temperature 0,
8,192 tokens, code 129d174 with that day's uncommitted fixes), every request and raw answer recorded:
- the title, the five ingredient lines under the source's heading "הגירסה שלי", their quantities and the one
  step are the caption's own words, "מג׳הול" included; the introduction, the two sponsor lines with their
  discount codes and the hashtags are left out; no review point;
- the category request answered `"dish": "קינוח מתוק עם ביצים וקמח"` (the recipe has neither) and
  "קינוחים · קינוחי כוסות ומוסים", although "משקאות" says that a coffee drink, sweet or on milk, belongs
  there and "קינוחים" says "לא משקאות": the known limitation again, corrected at review.

### 2026-11-04: dessert types, one candidate with definitions from ingredients and preparation

After the person reviewed the types of their desserts, the classifier's mistakes were of three kinds: cakes
called tarts (12, 34, 35, 42), cakes called cookies (25, 52), and creams for other desserts given a type
(22, 23; 9, chocolate bites, called a cup dessert). One bounded attempt to improve it for new imports,
measured with the category request alone, local `qwen3:8b`, two runs each, alternating.

- **Cases**, expected answers written before any run. **dev**: 29 of the person's desserts, expected the
  type they approved (a correction made in review counts as right only when the model itself answers it),
  and the two creams they left without a type; recipe 25 as completed from its page; 47 (a cream under a
  cheesecake's title, no type decided) shown, not scored. **Held out**, run only for the final check: 14
  invented recipes on the three confusions (a cheesecake on a crumb base, a lemon tart, an apple pie, a
  layered cake, muffins, cupcakes, a mug cake; cut-out cookies, no-bake balls; a pastry cream and a ganache
  for other desserts, a mousse, a trifle and a pudding served on their own).
- **The candidate**, written before any run and not reworded after: the current request plus general
  definitions that tell the kinds apart by ingredients and steps, naming no category (a baked or cooked
  batter is a cake, in single portions too, and so is a cheesecake or layered cake on a crumb base; a tart
  or pie is a pastry shell holding a filling; cookies and bites are many small pieces; a cream, frosting or
  filling for another dessert gets no type; a cream served on its own is a dessert).

| (run 1 / run 2) | Current request | Candidate |
|---|---|---|
| dev, 29 scored | 21 / 21 right, 8 / 8 wrong type | 17 / 19 right, 12 / 10 wrong type |
| held out, 14 | 11 / 10 right, 3 / 4 wrong type | 11 / 11 right, 3 / 3 wrong type |
| the 7 corrected in review (both runs) | 3 of 14 | 5 of 14 |

- **Better with the candidate**: three cakes (25, 34, 42) and the cupcakes (held out).
- **Worse**: its "batter" made cakes of the pancakes (28), the doughnuts (29) and the yeast ספינג׳ (43),
  the cottage-cheese ice cream (19) became a cup dessert, and the alfajores cheesecake (35) a tart.
- **Wrong with both**: the vanilla torte (12) is a tart; the muffins (held out) and the banana soufflé
  muffins (52) are cookies; the chocolate peanut-butter cups (9) are a cup dessert; every cream made for
  another dessert (22, 23, the pastry cream, the ganache) gets a type: in no run of either request did the
  model leave a dessert without a type, so "no subcategory" is not an answer it gives.

Not clearly better (worse on the person's own desserts), so **the current request stays**. Results, the
cases and the scripts: `data/evals/extraction/20261104-dessert-types/` (git-ignored: it holds the person's
recipes).

### 2026-11-03: dessert types and the healthy style, one candidate against the current request

The person replaced "קינוחים רגילים / בריאים" with six dessert types and a separate healthy-style attribute
(migration 0014), and asked for three separate decisions: what kind of dish it is, its category and (for a
dessert) its type, and whether it is in their healthy style. Measured with the category request alone on
drafts (no extraction, no website), local `qwen3:8b`, two runs each, alternating.

- **Cases**, with the expected answers written before any run: 19, of which 12 to look at while building
  the candidate and 7 **held out** until the final check. 13 of the person's saved recipes (their saved
  healthy or regular choice as the expected healthy style; the type judged from the dish), the evaluation
  cases 34 (date and oat balls) and 37 (oat and raisin cookies with butter and sugar), and four invented
  for this: a savory cottage-cheese and oat pie, oat, almond-butter and honey cookies, butter-and-sugar
  cookies with oats and dates, chocolate mousse cups. Butter-and-sugar sweets with oats or dates accept
  "no" or "not decided"; only "yes" is wrong.
- **The current request**, run with the new categories (for the category and the type) and with the old
  ones (its "בריאים / רגילים" choice is how it decided the healthy style until now).
- **One candidate**, written before any run and not reworded after: one request; the current rules plus
  three decisions in order (`kind`: drink, dessert, savory dish or other; the category and the type; and
  `healthy_style`: yes, no or unsure, with the person's own definition and "the whole recipe, never one
  ingredient"); a `kind` that disagrees with the category (a dessert outside the desserts, or the
  reverse) leaves the recipe unclassified.

| (run 1 / run 2) | Current request | Candidate |
|---|---|---|
| category, 12 to tune | 9 / 9 right, 3 / 3 wrong, 0 unresolved | 10 / 9 right, 2 / 3 wrong, 0 unresolved |
| category, 7 held out | 6 / 6 right, 1 / 1 wrong | 6 / 6 right, 1 / 1 wrong |
| dessert type, 13 desserts in the right category | 12 / 12 right, 1 / 1 wrong | 12 / 12 right, 1 / 1 wrong |
| healthy style, 13 desserts | 8 / 8 right, 5 / 5 wrong | 10 / 10 right, 3 / 3 wrong |
| one classification request | 1.3–1.6 s on average (median 1.3) | 1.7 s (median 1.6) |

- **Better with the candidate**: the brûlée tart (31), the oat and raisin cookies (37) and the
  butter-and-sugar date cookies are no longer called healthy-style; the savory pie was a light meal in one
  run of two (a dessert in every other run of both).
- **Worse with the candidate**: the person's healthy chocolate-chip cookies (21) became "no" in both runs.
- **Wrong with both**: the banana-date iced coffee (17) and the sahlab (50) are desserts in every run (the
  candidate's own `kind` said "dessert", so its check had nothing to catch: the model reads them as "a sweet
  dessert with banana and dates"); the cottage-cheese ice cream (19) and the blintzes (13) are "no" for
  the healthy style; the vanilla torte (12) is a tart; the savory protein pancakes (14) are a dessert (now)
  or a meat meal (candidate).
- **The types work with the current request**: 12 of 13, from the subcategories' descriptions alone; the
  new categories changed no main category answer (the same answers with the old and the new ones).

The candidate is better on the healthy style, but not on the category (the drinks, the person's own
example, stay wrong) or the type, and its "no" covered three of the person's five healthy desserts. Not
clearly better, so **the current request stays**: a new import gets a category and, for a dessert, a type
when one clearly fits; its healthy style stays "not decided", for the person. Results, the cases and the
scripts: `data/evals/extraction/20261103-dessert-classification/` (git-ignored: it holds the person's
recipes).

### 2026-11-01 (later): the text around the recipe for the category request; spreads, dips and sauces

Question: does the separate category request classify better when it also gets the text's own lines
that are not part of the recipe (the introduction, a remark such as "the side we make with schnitzel")?
Measured with the category request alone on saved drafts (no new extraction, no website fetching), the
same 79 drafts and the eight categories for every approach, two runs each, alternating:
- **tuning**: the 51 earlier cases (01–49 and the real captions), already seen while the change was designed;
- **fresh**: cases 50–61, written before measuring;
- **yours**: the 16 saved recipes in the notebook that have an imported original, compared with the
  category the person saved (not a verified answer: a recipe saved before a fitting category existed
  keeps its old one; the flavored butters, unclassified when saved, count as the new category).

The text around the recipe: the original's lines that the draft's own strings do not cover by half, in the
text's order, up to 500 characters, without lines of only hashtags, mentions, links or symbols and without
short labels like "מצרכים:"; inside the request's randomly named data tags, under its own mark, described
to the model as data. Two versions: with one more rule ("a category fits only when its description covers
this kind of dish; sharing ingredients, or being eaten at a similar meal, is not enough: no_fit"), and the
context alone.

| Set (run 1 / run 2) | Current request | Context and the rule | Context only |
|---|---|---|---|
| tuning, 51 | 41 / 42 right, 10 / 9 wrong, 0 unclassified | 41 / 42 right, 10 / 9 wrong, 0 | 43 / 43 right, 8 / 7 wrong, 0 / 1 |
| fresh, 12 | 6 / 6 right, 6 / 6 wrong, 0 | 3 / 5 right, 8 / 6 wrong, 1 / 1 | 7 / 7 right, 4 / 4 wrong, 1 / 1 |
| yours, 16 | 13 / 13 right, 3 / 3 wrong, 0 | 10 / 13 right, 5 / 3 wrong, 1 / 0 | 10 / 10 right, 5 / 4 wrong, 1 / 2 |

- **The rule made things worse** and was dropped: on the fresh cases 3 and 5 right instead of 6 and 6;
  it never made a dish that fits nothing unclassified, only clear ones (the chicken quinoa bowl, 58).
- **The context alone helps sides and savory dishes**: rice with vermicelli (43), green beans (44), ptitim
  (48) and the quinoa side (57) became sides in both runs, and the pie (10), the tortillas (20) and the
  avocado toast (24) were no longer called desserts. It also **breaks others**: the egg fried rice that is
  the meal (49) became a side in both runs, the fritters (19) a dessert, the ricotta shells (28) a meat
  meal; among the person's recipes the blintzes (13) came back unclassified, the buttercream (23) once a
  soup, and the banana iced latte (17) a drink (saved in "קינוחים בריאים"; a drink is defensible).
- **Neither leaves a dish that fits nothing unclassified**: majadra (11), pickles (26), chraime (31),
  lentil patties (45), sea bream (59), crackers (61), and the person's udon and stuffed onions always got
  a category.
- **Flavored butter** (50, and the person's own butters) was a dessert in every run of every approach.
  Pesto (51) was right with the current request in both runs; hummus (52) never (a dessert, or
  unclassified with the context).

Across all 79 drafts the current request and the context alone have as many right answers (60.5 against
60 on average); the context trades about three wrong categories for three unclassified clear ones, and
does worse on the person's own recipes. The improvement is not consistent, so **the current request
stays**. The implementation (with its tests) is kept on the branch `experiment/classification-context`,
for a stronger model. Results, scores and the drafts used: `data/evals/extraction/20261101-classification-context/`
(git-ignored: it holds the person's recipes); the fresh cases' extraction run: `20261101-152154`, where
every check other than the category passed.

### 2026-11-01: salads, soups and sides

`qwen3:8b` through Ollama, on the RTX 5060 Laptop, with the seven top-level categories (migration
0012). Runs `20261101-141716` (32 cases: 38–45 and every case near the new categories), `20261101-143317`
and `20261101-143402` (46–49 and 38). Besides full runs, the category request alone was asked again on
the first run's 29 drafts, so descriptions could be compared on the same drafts; logs in
`data/evals/extraction/20261101-category-variants.txt`.

**What works.** Every soup went to "מרקים" in every run, also with chicken (38) or beef (41) and the
legume soups (12, 47); every salad to "סלטים", also with cheese (04, 39), chicken (40) or tuna and egg
(46). Roasted potatoes (42) and ptitim (48) went to "תוספות". The chicken-and-rice pot (22) and the
harissa chicken with chickpeas (29) did not become sides. All other checks of these cases passed.

**What does not.**
- **A dish that fits no category is pushed into a new one** instead of staying unclassified: the
  lentil patties (45, a main course) went to soups every time, the majadra (11) to salads or soups, the
  pickles (26) to soups or salads, the fish (31) to meat meals or salads. Measured on the 18 earlier
  recipe cases, with the same drafts and two passes each: the old four categories got 13 and 14 right,
  2 and 2 wrong, 3 and 2 left unresolved; the seven got 14 and 13 right, 4 and 5 wrong, none unresolved.
  As many are right, but a wrong category replaces "unresolved", which the person had to classify anyway.
- **A side's role is not visible to the category request.** It sees the draft's title, ingredient lines
  and steps; "the side we always make with chicken" is usually in the introduction, which is not part of
  the draft. So sides are judged by what the dish is: rice with vermicelli (43) was a side in 1 of 3
  answers (otherwise a light meal), the green beans (44) never (soups or salads), and the egg fried rice
  that is the meal (49) became a side in 1 of 2 runs.
- **The model's own description of the dish sometimes breaks down**, more often than with four
  categories: avocado toast with eggs (24) once became "קינוח שוקולד", the spinach-cheese pie (10) "פשטידה
  מתוקה", and the tortillas (20) a dessert, as they sometimes did before.
- **Temperature 0 is not repeatable here:** the same request on the same drafts gave 23 and 21 of 29
  right.

**Descriptions compared** (the category request alone, 29 drafts, right of 29): as written (kept): 23,
21; described by the dish's form instead of naming ingredients: 19; as written without the ingredient
words and with "a stew, patties in sauce or pickles are not soup or salad": 19; that, with the dish
type (soup, salad, side dish, main course) asked before classifying: 23; "only a dish the recipe itself
calls a soup / a salad / a side": 21, 21. None was better than the first wording beyond the variation,
so it stays: it says the person's own rules most directly, and the person can refine it in the category
screen. Possible next steps: give the category request the introduction's short lines, so a side's role
is visible (a change to every import, to be measured on all cases), or classify with the Claude API (not
measured).

During these measurements Ollama stopped once with "CUDA error: unknown error"; it reloaded the model by
itself on the next request.

### 2026-10-26 (evening): dessert subcategories

The evaluation's categories now include "קינוחים רגילים" and "קינוחים בריאים" (ids 5 and 6, as in a new
database), and a case can expect a `subcategory` (or `subcategory_one_of`). Expected: healthy style for
the date-and-almond energy balls (05) and the almond-butter cookies (real-5); regular for the cakes,
cookies, brownies, the cheesecake, the torte and the salted honey tart; regular or none for the
tahini-almond cookies (15). **Four new cases written for this check and not used for tuning:** date and
oat balls (34, healthy), a classic date cake on white flour, sugar and butter (35, regular), banana
muffins on oats and almond flour with maple (36, healthy), oat and raisin cookies on butter, flour and
brown sugar (37, regular or none).

Two live runs of the 16 desserts (`20261026-130634`, `20261026-131059`): the category right in all 16,
the subcategory right in 14 of 16, the same in both runs. The two mistakes are the same kind: **one
ingredient word outweighs the whole recipe**. The date cake (35) and the oat cookies (37) went to
"קינוחים בריאים" although both are built on flour, sugar and butter. The salted honey tart stayed regular,
and every healthy-style dessert was found. One general change to the regular subcategory's description
("the whole recipe decides, also with dates, oats, honey or nuts beside flour, sugar and butter") was
tried on the same drafts and changed nothing, so the descriptions stay as first written; you can
refine them in the category screen.

### 2026-10-26 (afternoon): an ingredient introduction, an optional label, a vegan alternative

A real post the person imported (https://www.instagram.com/p/CLJ5G9rDi1a/, almond cookies), now the
private regression case real-5. Traced passage by passage: the text is cut correctly; the model's
labels were the same in three runs (`20261026-120025`, `-120048`, `-120108`); the mistakes come from
how the backend turned those labels into a draft:

| passage | model's label | before | cause | after |
|---|---|---|---|---|
| "אז מה צריך לכל הטוב הזה?" (before the ingredient list) | step heading | step 1 | the rule "a sentence labeled a heading is a step" (added for "מחממים תנור מראש.") ran before the rule that a heading heads what follows | an introduction: starts the list, in the original only |
| "אופציונאלי:" + "שוקולד צ׳יפס…" | tip + ingredient | "שוקולד צ׳יפס…" (the label lost) | only purpose words ("להגשה:") kept a label with its item | "אופציונאלי: שוקולד צ׳יפס לבן/שברי שקדי/שברי אגוזים" |
| "*אופציה טבעונית:" + flax mixture + "זה תחליף לביצה" | tip + ingredient + tip | an extra ingredient, and a stray note "זה תחליף לביצה" | nothing kept a note's label with the rest of its line after the steps | one note: "אופציה טבעונית: כף פשתן טחון+3 כפות מים=לערבב ולתת לו לנוח 6 דקות. זה תחליף לביצה" |
| "תהנו ❤️" | tip | a note | the prompt calls sign-offs not part of the recipe; the model disagreed | left out |

The text states the replacement itself ("זה תחליף לביצה"), so the note keeps exactly that; the egg
stays in the list, and nothing is inferred or added.

**Checks.** The same saved answers rebuilt with the code before and after the fix (no model calls):
the two full runs of 2026-10-25 went from 7 and 6 problems to 4 and 4 (every check passed in 31 of 37
cases in both, before 28 and 29); no draft changed except three sign-offs removed ("בתיאבון!" in 07 and
11, "וזהו😍 נכון קל?" in real-2); real-5 from 6 problems to none. Live afterwards
(`20261026-121043`, 12 varied cases): every check passed in 10, case 18 still starts with "מחממים תנור
מראש."; the two misses are known ("שמרו לימים החמים" kept in 21, the source gap "עלה גפן" in 26). real-5
passed every check in all three live runs since. Through the page on a test database: the post read
in 7.3 s, the draft as above, saved and unchanged after a reload. real-5 is not independent: the fix
was made for it; the synthetic unit tests cover each rule and what it must not touch.

### 2026-10-26: Instagram links, end to end

Reading the post and extracting the recipe are measured separately. **Reading:** the three supplied
posts were read 3 of 3 times through the app's API (and `DPbKEn-CnUt` twice more through the page),
always from the post page and byte-identical to the captions saved in milestone 1; a nonexistent
post was reported unavailable. **Extraction from what was read** (local `qwen3:8b`, the same as for
pasted text), scored against the expectations of the local cases these captions already are:

| post | case | category | checks |
|---|---|---|---|
| Cm1mCdCpSzJ (vanilla torte) | real-1 | קינוחים | every check passed |
| DANUmOOIcRM (salted honey tart) | real-3 | קינוחים | every check passed |
| /reel/DPbKEn-CnUt (shoulder and ptitim) | real-2 | ארוחות בשריות | 3 problems: the sign-off "וזהו😍 נכון קל?" and two calls to action kept as notes |

**Not independent:** these three captions are the real-1, real-2 and real-3 cases used while
developing the extraction and the categories. What is new here is the reading (the `/reel/` address
form, the failure path, the server setting), not the extraction quality. No new Instagram posts were
available to test with.

### 2026-10-26: composed titles

A small change to the title instruction (name the dish itself, in the text's spelling, from the
introduction too; no occasion, story or hype) and one backend rule (a title that starts no line of the
text is always flagged as composed). Checked on the 8 existing cases whose title matters (6 without a
title line, 2 with one) and on **5 new examples written for this check and not used for tuning**
(a holiday couscous, a "viral" English side dish, a sponsored drink, a lunch that never names its dish,
and a written title after a hype line); two live runs each (`20261026-083126`, `20261026-083411`), the
new examples also once with the previous prompt. The evaluator accepts any composed title, so titles
were read by hand:

| case | before | after (both runs unless noted) |
|---|---|---|
| your coffee drink (real-4) | משקה טרנדי לכבוד היום האחרון של הקיץ | משקה טרנדי של שייק בננה תמר ואייס קפה |
| shoulder and ptitim (real-2) | מנה של הצלי כתף ופתיתים | צלי כתף ופתיתים |
| green shakshuka (14, written title) | ארוחת בוקר של שישי: שקשוקה ירוקה | שקשוקה ירוקה |
| tortillas (20) | הפיצה המקופלת | טורטיה מקופלת / הפיצה המקופלת |
| shakshuka (07), cheesecake (30) | שקשוקה; עוגת הגבינה הקרה עם הפירורים | שקשוקה; עוגת גבינה קרירה עם פירורים |
| avocado toast (24) | טוסט avocado | טוסט avocado (now always flagged as composed) |
| new: sponsored matcha | אייס מאצ'ה עם חלב שקדים ודבש | the same |
| new: viral potatoes | crispy smashed potatoes with garlic yogurt | Crispy smashed potatoes with garlic yogurt |
| new: holiday couscous | koskos עם ירקות שורש ונענע | the same (a misspelling of "קוסקוס"; flagged) |
| new: lunch with no dish name | ארוחת צהריים זריזה ממה שהיה במקרר | the same (the model labels that line a title) |
| new: written title after hype | Lemon Ricotta Pancakes | the same |

Every composed title was flagged for review in every run (before the backend rule, three were flagged
only as "not found in the text"). Remaining: the coffee title still starts with the caption's own
"משקה טרנדי"; a composed title is typed by the model and can be misspelled ("koskos"); a lunch that
never names its dish gets its introduction line as the title. Other checks on these cases were
unchanged (the sign-offs of real-2 kept as notes in one run, a known issue).

### 2026-10-25 (evening): your reorganized categories

Your four categories: "קינוחים", "ארוחות בשריות" (formerly "בישולים", same id), "ארוחות קלילות" (now
dairy **or egg**) and "משקאות" (added by you). Local `qwen3:8b`, two live runs of all 37 cases
(`20261025-222407`, `20261025-223146`), 100% on the GPU, about 457 s per run, scored against the
expected categories above. The first request (labels and recognition) did not change; the category
request has the new descriptions and a no-fit example without "a drink". **Not independent:** the
descriptions were chosen by replaying the category request on the afternoon runs' drafts of these
same cases, so these category numbers are after tuning.

| | run 1 | run 2 |
|---|---|---|
| recipe texts imported | 34/34 | 34/34 |
| texts that are not recipes refused | 3/3 | 3/3 |
| category (within drafts) | 41/42 | 41/42 |
| problems (not minor) | 7 | 6 |
| cases where every check passed | 28 of 37 | 29 of 37 |
| ingredient lines, quantities | 298/298, 298/298 | 298/298, 298/298 |

**The cases you named, five runs each** (the two above and three more of just these):

| case | category, 5 runs | every check passed |
|---|---|---|
| your coffee drink (real-4) | משקאות 5 | 5 |
| lemonade (06), frozen lemonade (21), watermelon drink (27) | משקאות 5 each | 5, 0 ("שמרו לימים החמים" kept as a note), 5 |
| shakshuka (07, 14) | ארוחות קלילות 5 each | 4 ("בתיאבון!" once), 5 |
| cheesecake (30), salted honey tart (real-3), vanilla torte (real-1), salted-caramel brownies (23) | קינוחים 5 each | 5 each |
| ricotta-stuffed shells (28) | **ארוחות בשריות 5** (expected ארוחות קלילות) | 0 |

**The one category miss is consistent.** Asked alone, the model gives "ארוחות בשריות" 0.83–0.92 for
the shells right after summing them up as "pasta and cheese". Swapping the two categories' ids moves
the answer with the category, so it is the content, not the position; with a neutral name in place of
"ארוחות קלילות" it chose that category for one of the two drafts, so the word "light" plays a part.
Descriptions that name cheese-filled shells, a description that starts with "ארוחות חלביות", a yes/no
answer per category and quoting the description's words did not fix it without breaking others.

**Categories measured alone** (the category request only, on the same 68 drafts): plainer
descriptions 59–61 right; the chosen ones 65 right, 2 wrong (the shells; the chraime once), 1 left
unclassified. The changes that helped: concrete dishes in each description (פרגיות, מאפינס, פשטידות,
frozen lemonade), "לא מתוקות" instead of "מלוחות" (which also means "salty": the salted honey tart was
put with the savory meals), and no drink in the prompt's example of a recipe with no category.

Other findings are the afternoon's: sign-offs kept as notes (07 once, 11, 21, real-2), the short title
"בראוניז" (13), "תיבול: ..." as its own group (20), and the source gaps the word list cannot see.

### 2026-10-25 (afternoon): recognition apart from categories, your category meanings, passage context

Local `qwen3:8b`, two live runs of all 37 cases (`20261025-162540`, `20261025-163351`), 100% on the
GPU (6.19 GB, context 8,192), about 490 s per run. Everything is scored by today's checks and
today's expected categories; the earlier runs were re-scored, not rerun. **Imports are counted apart
from accuracy within the drafts**: a refused recipe stays a failed case.

**The 30 cases used while developing** (run 1 / run 2):

| | previous round (morning) | this round |
|---|---|---|
| recipe texts imported | 29/29, **28/29** (your drink caption refused) | 29/29, 29/29 |
| texts that are not recipes refused | 1/1 | 1/1 |
| problems (not minor) | 27 / 27 | 7 / 9 |
| failed checks, all (minor) | 36 / 36 (9 / 9) | 11 / 15 (4 / 6) |
| cases where every check passed | 15 / 14 | 24 / 21 |
| ingredient lines (within drafts) | 249/255, 244/250 | 251/251 each |
| groups | 43/47, 42/46 | 46/47 each |
| category | 26/36, 26/35 | 34/36, 32/36 |
| warnings | 9/16, 7/14 | 14/16, 13/16 |

**The 7 fresh cases** (27–33, independent: written for this round, kept unread until these runs).
As measured: every recipe imported (5/5) and both texts that are not recipes refused (2/2) in both
runs; 5 problems per run; every check passed in 4 of 7. With one evaluator correction (a line written
in two groups was scored as out of order; the drafts are the same) 3 problems per run. What they
missed: ricotta-stuffed shells and a fish chraime both went to "בישולים" (the first is a dairy meal,
the second has no clear fit; having a category, it also lacks the "unclassified" review point, a minor
finding). The sugar that the chraime's list leaves out was pointed out. After the measurement one fix came from case 27 (a heading before
the ingredients labeled as a preparation heading now heads the ingredients): 2 problems per run, 5 of
7 passing; those numbers are no longer independent.

**Repeated imports** through the app's own path, each after a different one: your drink caption
imported 10 of 10 times, unclassified, every check passing; cases 14, 18 and 24 passed every check
4 of 4 times; case 26 imported 4 of 4 (the vine leaf it leaves out of its list is never pointed out,
and once in 4 it got a category); the fresh drink 3 of 3; the restaurant review, the market haul and
the workshop announcement were refused 3 of 3 times each.

**Recognition.** With the categories in the same request, the model's first decision about your
caption, `is_recipe`, was false in 8 of 12 imports (P(true) 0.10–0.80). Recognizing and labeling
without the categories: true 12 of 12 (P(true) at least 0.995); other drinks and the restaurant review
were unaffected. No second check for suspicious rejections was needed.

**Categories, measured alone** on the same 60 drafts against the re-annotated expectations: your
descriptions with the "description decides" instruction and a dish summary that names the main
ingredient, 54 right, 5 wrong, 1 unresolved; your descriptions with the earlier instructions 46–49
right; the morning's descriptions 44. Still wrong in the final runs: majadra (both runs) and once a
spinach-cheese pie under "בישולים", the frozen lemonade under desserts (both runs), and in the fresh set
the stuffed shells and the chraime under "בישולים".

**Other remaining failures**: "בתיאבון!", a call to action or an introduction sentence kept as a note
(11, 13, 21, real-2); "תיבול: מלח, פלפל שחור, אורגנו יבש" as its own group (20); once the short title
"בראוניז" (13); source gaps the word list cannot see ("cream", "עלה גפן"). A composed title can contain
a word that is not in the text ("טוסט avocado" for case 24); its review point now says so.

### 2026-10-25: source gaps, purpose lines, servings evidence, notes, categories

Local `qwen3:8b`, two live runs of all 30 cases (`20261025-133235`, `20261025-133925`), 100% on the
GPU (6.19 GB, context 8,192), about 400 s per run. Every column is scored by the corrected checks
(see "How the check works"); the baseline and the previous round were re-scored, not rerun. "App
fixes offline" turns the previous round's saved model answers into drafts with today's backend:
the application fixes alone, without the category change or the model's run-to-run variation.

**The 25 cases used while developing** (run 1 / run 2):

| | baseline | previous round | app fixes offline | final, live |
|---|---|---|---|---|
| problems (not minor) | 69 / 74 | 17 / 18 | 12 / 13 | 12 / 12 |
| failed checks, all (of them minor) | 83 / 87 (14 / 13) | 25 / 26 (8 / 8) | 14 / 14 (2 / 1) | 12 / 12 (0 / 0) |
| cases where every check passed | 5 / 5 | 10 / 11 | 15 / 16 | 16 / 15 |
| source gaps pointed out, nothing added | 3/6 | 3/6 | 6/6 | 6/6 |
| tips kept whole | 16/18 | 17/18, 16/18 | 18/18 | 18/18 |
| facts and servings | 27/32 | 27/32 | 32/32 | 32/32, 31/31 |
| category | 23/30, 24/30 | 24/30, 25/30 | 24/30, 25/30 | 26/30, 26/29 |
| unnecessary / duplicate review points | 12 / 8 each | 1, 0 / 0 | 1, 0 / 0 | 0 / 0 |
| no draft for a recipe | 0 | 0 | 0 | 0 / 1 |

**The 5 fresh cases** (22–26, written independently for this round and kept unread until the live
runs): 10 problems and 4 minor findings in each run, every check passed in 1 of 5. What they
showed: a purpose label and its one item on a line ("להגשה: גלידת וניל", "To garnish: fresh basil
leaves") became a one-item group instead of one ingredient line; "Ingredients" stayed a group name
beside a second group; "נבטי חמניות" in the list did not count as listing "נבטים" (a needless review
point); the model took an introduction sentence as the title (24), labeled the list inside an
introduction as ingredients (26) and gave pickles a category (26). The first three were fixed in
the backend after this measurement; offline on the same answers the fresh cases then have 4
problems in each run and 2 of 5 pass every check. Those numbers are no longer independent.

**Category descriptions, measured alone.** The same 50 drafts (2 runs × 25 cases) classified once
with the old and once with the new descriptions: old 38–40 right, 8–9 wrong, 2–5 unresolved where
a category fits (the model varies between runs even at temperature 0); new 43 right, 7 wrong, none
unresolved. Every dessert was classified, including the salted honey tart (before: "בישולים"), and
no drink or savory dish went to desserts. Four other wordings were tried and rejected: one put
lemonade under desserts, one a savory tortilla dish, and adding "a full meal or a small one" to the
dish summary made both worse. What remains: light savory meals (shakshuka, fritters, tortillas)
still go to "בישולים" in 7 of 50.

**Still wrong in the final runs** (both runs unless noted): introductions or sign-offs kept as notes
(11 "בתיאבון!", 13, 21, real-2, 24); light meals under "בישולים" (07, 19, 20, 14 in run 1, 26);
"תיבול: מלח, פלפל שחור, אורגנו יבש" made its own group (20); "מחממים תנור מראש." labeled a heading,
so it is missing from the steps (18); the title "ארוחת בוקר של שישי" instead of the dish (14);
source gaps not pointed out where the word is not in the ingredient list ("cream", "עלה גפן");
"זית" pointed out from the color "ירוק זית" (26); and in run 2 the user's own caption (real-4) was
refused as not a recipe, the model having labeled every passage "not part of the recipe". That
happened in 2 of the 24 saved runs that include it; the page shows "לא נמצא מתכון בטקסט." and
keeps the text, which can be imported again or saved with "שמירה בלי עיבוד".

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
