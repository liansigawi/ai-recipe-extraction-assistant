# Extraction quality

How well Claude turns pasted recipe text into a draft, measured separately from the software
tests. The software tests (`uv run pytest`) prove that the backend checks and saves whatever the
model answers correctly; they never call Claude. This check calls the real model, so its results
depend on the model and the date, and each run costs money.

## How the check works

`uv run python -m evals.run_extraction` (from `backend/`) sends each case's text through the same
code as a real import: one Claude request (`app/extraction/claude.py`), then the backend's own
checks (`app/extraction/review.py`). Then `evals/checks.py` compares the draft with expectations
written by hand, and reports:

| Finding | Meaning |
|---|---|
| `omission` | an expected ingredient line, time, temperature or note is missing or was changed |
| `wrong_quantity` | a quantity differs from the one written in its line, or the model gave one that is not in the line |
| `addition` | more ingredient lines than the text has, or an ingredient the text does not list (e.g. one only the steps mention) |
| `not_in_source` | the backend could not find a line of the draft in the original text: reworded or invented |
| `unwanted_text` | hashtags, mentions, calls to action or injected instructions ended up in the recipe |
| `classification` | a different category than expected, or a category where it should stay unresolved |
| `missing_flag` | something that should have been flagged for review was not |
| `structure`, `title` | ingredient or step groups, or the title, differ from the text's own |

At most 15 requests per run, one at a time. Each case's raw answer, the draft and the findings
are saved in `data/evals/extraction/<run>/` with a `report.md`.

## The cases

Ten invented texts, in `backend/evals/cases/` (each `<name>.txt` + `<name>.json`):

| Case | What it checks |
|---|---|
| 01 yeast cake with groups | two ingredient groups, fractions, a time range, pan size and substitution as notes; intro, hashtags and a mention left out |
| 02 stew, pressure cooker or pot | alternative methods in separate passages become separate step groups with their own times; no-quantity line; reused cooking liquid |
| 03 ingredient only in steps | strawberries used in the steps but not listed: flagged, not added; an "or" inside a line kept |
| 04 English quick salad | English kept as written; "to taste" is not an amount; an en-dash range |
| 05 energy balls | a sweet snack between two categories: unresolved or desserts; no new category |
| 06 lemonade | a drink fits no category: must stay unresolved |
| 07 caption without title | composed title flagged; emoji bullets dropped; calls to action and mentions left out |
| 08 instructions inside the text | the text tells the model to create a category and change amounts: it must not |
| 09 not a recipe | a restaurant review: "not a recipe", nothing invented |
| 10 missing oven details | no temperature or time given: flagged as missing, never filled in |

Three real captions, the milestone-1 Instagram posts, in `data/evals/local-cases/` (git-ignored,
because they are other people's content): a vanilla torte with three ingredient groups and
strawberries only in the steps, a beef and ptitim dish with no title line and the cooking-method
alternative inside one sentence, and a salted honey tart with `|` headings and two different
apostrophes (`גר’`, `גר׳`). Their expectations quote each line from the caption itself.

Run all thirteen with:

```bash
cd backend
uv run python -m evals.run_extraction --cases-dir ../data/evals/local-cases
```

## Results

Not run yet: the check needs an Anthropic API key on this computer (README, "Connect the Claude
API"). Results will be recorded here with the date, the model, and every finding.
