@echo off
rem Updates the public, read-only notebook: exports the chosen recipes, builds the site, publishes it to the
rem same address and checks it. Options: --add ID, --remove ID, --list, --no-deploy (docs\public-notebook.md).
uv run --directory "%~dp0backend" python -X utf8 -m scripts.publish_public %*
exit /b %errorlevel%
