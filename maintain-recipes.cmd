@echo off
rem Brings saved recipes up to the importer's current rules, with a report first (docs\maintenance.md):
rem   audit (read-only), apply <batch folder> [--exclude ID ...] [--only ID ...] --yes, undo <batch folder> --yes
uv run --directory "%~dp0backend" python -X utf8 -m scripts.maintain_recipes %*
exit /b %errorlevel%
