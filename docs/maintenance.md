# Bringing saved recipes up to date

When the importer's rules improve, the recipes you already saved do not change by themselves. A maintenance
batch proposes the same improvements for them, shows each change before anything happens, and applies only
what you approve, in place.

```powershell
.\maintain-recipes.cmd audit                                            # read-only: proposals and a report
.\maintain-recipes.cmd apply data\maintenance\<batch> --yes             # everything in the batch
.\maintain-recipes.cmd apply data\maintenance\<batch> --exclude 12-type 34-type --yes
.\maintain-recipes.cmd apply data\maintenance\<batch> --only 51-steps 51-ingredients --yes
.\maintain-recipes.cmd undo data\maintenance\<batch> --yes
.\maintain-recipes.cmd propose-types data\maintenance\reviewed-types.json   # read-only: a batch from a reviewed list
```

(`backend/scripts/maintain_recipes.py`; `--database <file>` before the command works on another notebook file,
such as a test copy. Without `--yes`, apply and undo change nothing.)

## What the audit proposes

It opens the notebook read-only and writes `data/maintenance/<batch>/` (git-ignored, like the rest of `data/`):
`report.html` (open it in a browser), `batch.json` (the proposals), `before.json` and `after.json` (snapshots
of the recipes before this maintenance update and as they would be if every proposal were approved: neither is
a model draft from an import, and no draft is reconstructed). Each change has its own id:

- **`<id>-steps`, `<id>-ingredients`**: for a recipe imported from a page's recipe data (JSON-LD or
  microdata), what the importer makes today of the data saved with the import: shortcodes, photo captions and
  sponsor lines out of the steps, and the steps and ingredient groups as the page's own lists show them
  (`website.checked_with_page`). The page is read again only for that: the saved data does not hold its lists.
  The report says whether the page's data is still what was saved, and whether the current text is the
  import's own (every line in the saved original) or may hold your edits.
- **`<id>-oil`**: the line the oil rule (`app/extraction/derived.py`) adds to a new import with these steps.
- **`<id>-type`**: for a dessert without a type, the type the local classifier gives in two requests that
  agree; otherwise nothing (listed as unresolved). A title word that points to another type is flagged. The
  main category, the healthy style and a type you set are never changed. Invented samples are left out.

The same code as an import makes every proposal; nothing is re-extracted.

## Reviewed dessert types

Two classifier answers that agree are not evidence that they are right. A reviewed list of types (JSON:
`{"basis": "...", "assignments": [{"id": 12, "type": "עוגות", "basis": "...", "note": "..."}]}`, with `"type": null`
to leave one unassigned) becomes a batch of its own with `propose-types`, applied and undone like any other.
Each assignment says what it rests on (the classifier's proposal confirmed in review, or a correction made in
review), so a reviewed correction is never shown as the model's prediction. A recipe that is not a dessert or
already has a type gets nothing. The earlier batch's type proposals are then marked as replaced by it: its
report says so, and applying that batch skips them.

## The report shows where things stand

After an apply or an undo, `report.html` is written again: each change says whether it is applied (and when)
or still a proposal, or replaced by a later batch.

## What applying does, and never does

- First a backup of the notebook (`recipes.backup-<time>-before-maintenance-<batch>.db`), checked: intact, the
  same recipes. If that fails, nothing changes.
- Each recipe is updated in place, only in the fields of its approved changes (ingredients, steps, the type),
  and its last-saved time is updated. Its id, status, media and cover, credits and sources, cooked mark,
  imported original and place in the public selection stay as they are.
- A recipe whose content changed after the report is skipped and named: make a new report. A change already
  applied is not applied again (applying the batch twice adds nothing). What was left out can be applied later.
- `applied-<time>.json` in the batch folder records what was written, for this notebook file only.
- Undo puts back what the batch wrote, its last-saved time included, wherever the recipe still holds exactly
  what the batch wrote; a recipe you edited since is left as it is. The backup is there for a full restore.
