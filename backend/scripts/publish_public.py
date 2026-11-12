"""Update the public, read-only notebook in one step: export the chosen recipes, build the site, publish it
to the same address, and check that address. docs/public-notebook.md explains the whole flow.

From the project root:

    .\\publish-notebook.cmd               export, build, publish and check
    .\\publish-notebook.cmd --add 18 19   first add saved recipes 18 and 19 to the selection
    .\\publish-notebook.cmd --remove 12   first take recipe 12 out of the selection
    .\\publish-notebook.cmd --list        every recipe: can it be published, is it chosen
    .\\publish-notebook.cmd --no-deploy   export and build only (then `npm run preview:public` in frontend/)

(The same from backend/: uv run python -X utf8 -m scripts.publish_public ...)

Each step starts only when the one before it succeeded. The site is built into a new folder and checked
(only the expected files, every picture it names, no key or local path in any file) before it replaces the
previous build, and Cloudflare Pages moves the address to a new version only once all of it is uploaded.
So a failed export, build, check or upload leaves the published notebook as it was.

Hosting: Cloudflare Pages (free plan; static files only), uploaded with Wrangler, frontend/'s dev dependency.
One-time setup: a free Cloudflare account, then `npx wrangler login` in frontend/. Wrangler keeps that login
in your user profile, never in this project or in the published files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from sqlalchemy.orm import Session

from app import crud, media
from app.config import REPO_ROOT, load_settings
from app.errors import ApiError
from scripts import public_pictures
from scripts.export_public import ExportError, Selection, export_notebook, list_candidates, open_read_only, publishable, read_selection

FRONTEND = REPO_ROOT / "frontend"
DEFAULT_PROJECT = "recipe-notebook"  # the Cloudflare Pages project, chosen at the first publication
BRANCH = "main"  # the project's production branch: a deployment to it is what the public address shows
SITE_RECORD = "site.json"  # in the public-notebook folder: the project, its address, the last publication
# Every file a build may hold; anything else stops the publication.
SITE_FILES = re.compile(r"^(index\.html|favicon\.svg|notebook\.json|assets/[\w.-]+\.(js|css|woff2)|media/[0-9a-f]{64}\.(jpg|png|webp|gif))$")
LIVE_WAIT_S = 90  # how long the new version may take to appear at the address

Runner = Callable[..., subprocess.CompletedProcess[str]]
Getter = Callable[..., httpx2.Response]


class PublishError(Exception):
    """A step failed: what happened, for the person running the command."""


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """A program, with its output captured. Wrangler sends no usage statistics."""
    environment = {**os.environ, "WRANGLER_SEND_METRICS": "false", **(env or {})}
    return subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")


def tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise PublishError(f"{name} was not found. Install Node.js (docs/setup.md, section 'Requirements') and run npm install in frontend/.")
    return found


def tail(result: subprocess.CompletedProcess[str], lines: int = 25) -> str:
    text = (result.stdout + "\n" + result.stderr).strip().splitlines()
    return "\n".join(f"    {line}" for line in text[-lines:])


def wrangler(*args: str) -> list[str]:
    return [tool("npx"), "--no-install", "wrangler", *args]


# --- The selection -----------------------------------------------------------------------------------


def change_selection(folder: Path, database_path: Path, add: list[int], remove: list[int]) -> Selection:
    """--add and --remove: the selection file, changed and written back. All of them, or none if one is refused."""
    path = folder / "selection.json"
    selection = read_selection(path)
    engine = open_read_only(database_path)
    try:
        with Session(engine) as session:
            for recipe_id in add:
                try:
                    recipe = crud.get_recipe(session, recipe_id)
                except ApiError:
                    raise ExportError(f"The notebook has no recipe {recipe_id}.") from None
                why = publishable(recipe)
                if why is not None:
                    raise ExportError(f"Recipe {recipe_id} cannot be published: {why}.")
                if recipe_id not in selection.recipes:
                    selection.recipes.append(recipe_id)
    finally:
        engine.dispose()
    for recipe_id in remove:
        if recipe_id not in selection.recipes:
            raise ExportError(f"Recipe {recipe_id} is not in the selection.")
        selection.recipes.remove(recipe_id)
        if recipe_id in selection.show_processing:
            selection.show_processing.remove(recipe_id)
    path.write_text(json.dumps(selection.model_dump(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selection


def describe(notebook: dict) -> list[str]:
    """What becomes public, recipe by recipe: its credit, its original text or not, its cover."""
    lines = []
    for recipe in notebook["recipes"]:
        credit = next((s for s in recipe["sources"] if s["creators"]), None)
        who = ", ".join(c["username"] and f"@{c['username']}" or c["name"] for c in credit["creators"]) if credit else "no credit"
        original = "original text public" if recipe["original"] else "no original text"
        cover = recipe["media"][0] if recipe["media"] else None
        picture = (
            "no picture" if cover is None
            else "a still from its video" if cover["kind"] == "video"
            else "your uploaded picture, without its metadata" if cover["origin"] == "upload"
            else f"picture from the {cover['origin']}"
        )
        lines.append(f"  {recipe['id']:>4}  {recipe['title']}  ({who}; {original}; {picture})")
    return lines


# --- Build and check ------------------------------------------------------------------------------------


def build_site(folder: Path, runner: Runner = run) -> Path:
    """The site, built into a new folder and checked; only then does it replace the previous build."""
    partial = folder / "site.partial"
    if partial.exists():
        shutil.rmtree(partial)
    result = runner([tool("npm"), "run", "build:public", "--", "--outDir", str(partial)], FRONTEND, {"PUBLIC_NOTEBOOK_FOLDER": str(folder)})
    try:
        if result.returncode != 0:
            raise PublishError("The build failed:\n" + tail(result))
        check_site(partial, folder / "export")
    except PublishError:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    site = folder / "site"
    if site.exists():
        shutil.rmtree(site)
    partial.rename(site)
    return site


def secrets() -> list[str]:
    """Values that must never be in a published file: the API keys this computer has."""
    values = [os.environ.get(name, "") for name in ("ANTHROPIC_API_KEY", "RECIPES_ANTHROPIC_API_KEY", "CLOUDFLARE_API_TOKEN")]
    key = load_settings().anthropic_api_key
    values.append(key.get_secret_value() if key is not None else "")
    return [value for value in values if len(value) >= 8]


def check_site(site: Path, export: Path) -> None:
    """Only the expected files, the exported recipes unchanged, every picture they name and no other, the
    page's own files present, and no key or local folder name anywhere."""
    files = sorted(path.relative_to(site).as_posix() for path in site.rglob("*") if path.is_file())
    problems = [f"a file that does not belong in it: {name}" for name in files if not SITE_FILES.match(name)]
    if "index.html" not in files or "notebook.json" not in files:
        raise PublishError("The build has no index.html or notebook.json.")
    if (site / "notebook.json").read_bytes() != (export / "notebook.json").read_bytes():
        problems.append("its notebook.json is not the export's")
    notebook = json.loads((site / "notebook.json").read_text(encoding="utf-8"))
    named = {ref["url"] for recipe in notebook["recipes"] for item in recipe["media"] for ref in (item["file"], item["thumbnail"]) if ref}
    present = {name for name in files if name.startswith("media/")}
    problems += [f"a picture a recipe names is missing: {name}" for name in sorted(named - present)]
    problems += [f"a picture no recipe names: {name}" for name in sorted(present - named)]
    # No picture says where it was taken; an uploaded one carries nothing but its pixels.
    uploads = {ref["url"] for recipe in notebook["recipes"] for item in recipe["media"] if item["origin"] == "upload" for ref in (item["file"], item["thumbnail"]) if ref}
    for name in sorted(present & named):
        data = (site / name).read_bytes()
        if public_pictures.location_in(data):
            problems.append(f"{name} carries the place it was taken (GPS)")
        if name in uploads and (left := public_pictures.metadata_in(data)):
            problems.append(f"{name}, an uploaded picture, carries {', '.join(left)}")
    for link in re.findall(r'(?:src|href)="([^"]+)"', (site / "index.html").read_text(encoding="utf-8")):
        if not link.startswith("./") or link[2:] not in files:
            problems.append(f"index.html links to {link}, which is not a file of the site")
    forbidden = [(value.encode(), "an API key") for value in secrets()]
    forbidden += [(text.encode(), "a folder of this computer") for root in (REPO_ROOT, Path.home()) for text in (str(root), root.as_posix())]
    for name in files:
        content = (site / name).read_bytes()
        problems += [f"{name} contains {what}" for value, what in forbidden if value in content]
    if problems:
        raise PublishError("The built site did not pass its check:\n" + "\n".join(f"    {p}" for p in problems))


# --- Publish and check the address ---------------------------------------------------------------------------


def check_login(runner: Runner = run) -> None:
    result = runner(wrangler("whoami"), FRONTEND)
    output = result.stdout + result.stderr
    if result.returncode != 0 and "wrangler" in output.lower() and "not found" in output.lower():
        raise PublishError("Wrangler is not installed: run npm install in frontend/.")
    if result.returncode != 0 or "not authenticated" in output.lower():
        raise PublishError(
            "Wrangler is not logged in to Cloudflare. Once, in frontend/: npx wrangler login (it opens the browser "
            "to allow access to your free Cloudflare account). Then run this command again."
        )


def project_domains(runner: Runner = run) -> dict[str, str | None]:
    """The account's Pages projects and each one's *.pages.dev address."""
    result = runner(wrangler("pages", "project", "list", "--json"), FRONTEND)
    start = result.stdout.find("[")
    if result.returncode != 0 or start < 0:
        raise PublishError("Could not list the Cloudflare Pages projects:\n" + tail(result))
    projects: dict[str, str | None] = {}
    for item in json.loads(result.stdout[start:]):
        name = next((item[key] for key in ("Project Name", "name", "project_name") if key in item), None)
        domain = re.search(r"[a-z0-9-]+\.pages\.dev", json.dumps(item))
        if name:
            projects[name] = domain.group(0) if domain else None
    return projects


def deploy(site: Path, project: str, runner: Runner = run) -> str:
    """Upload the site as the project's production version; the address of the project."""
    domains = project_domains(runner)
    if project not in domains:
        created = runner(wrangler("pages", "project", "create", project, "--production-branch", BRANCH), FRONTEND)
        if created.returncode != 0:
            raise PublishError(f"Could not create the Cloudflare Pages project {project}:\n" + tail(created))
        domains = project_domains(runner)
    result = runner(
        wrangler("pages", "deploy", str(site), "--project-name", project, "--branch", BRANCH, "--commit-message", "Public notebook update", "--commit-dirty=true"),
        FRONTEND,
    )
    if result.returncode != 0:
        raise PublishError("The upload to Cloudflare failed:\n" + tail(result))
    domain = domains.get(project)
    if domain is None:  # the deployment's own address is <id>.<project's address>
        found = re.search(r"https://[a-z0-9]+\.([a-z0-9-]+\.pages\.dev)", result.stdout + result.stderr)
        if found is None:
            raise PublishError("The upload finished, but its address was not in Wrangler's answer:\n" + tail(result))
        domain = found.group(1)
    return f"https://{domain}"


def check_live(url: str, export: Path, get: Getter, sleep: Callable[[float], None], wait: float | None = None) -> None:
    """The address shows the version just built: its recipes, its page and every picture."""
    notebook = json.loads((export / "notebook.json").read_text(encoding="utf-8"))
    deadline = time.monotonic() + (LIVE_WAIT_S if wait is None else wait)
    while True:
        try:
            response = get(f"{url}/notebook.json", params={"v": notebook["exported_at"]}, timeout=20, follow_redirects=True)
            shown = response.json().get("exported_at") if response.status_code == 200 else f"HTTP {response.status_code}"
        except (httpx2.HTTPError, ValueError) as error:
            shown = str(error) or type(error).__name__
        if shown == notebook["exported_at"]:
            break
        if time.monotonic() > deadline:
            raise PublishError(f"{url} does not show the new version yet (it answered: {shown}). Look again in a few minutes.")
        sleep(5)
    page = get(f"{url}/", timeout=20, follow_redirects=True)
    if page.status_code != 200 or 'id="root"' not in page.text:
        raise PublishError(f"{url}/ did not answer with the notebook's page (HTTP {page.status_code}).")
    for recipe in notebook["recipes"]:
        for item in recipe["media"]:
            for ref in (item["file"], item["thumbnail"]):
                if ref is not None:
                    picture = get(f"{url}/{ref['url']}", timeout=20, follow_redirects=True)
                    if picture.status_code != 200 or len(picture.content) != ref["size_bytes"]:
                        raise PublishError(f"{url}/{ref['url']} did not answer with the picture (HTTP {picture.status_code}).")


# --- The command ------------------------------------------------------------------------------------------------


def publish(folder: Path, *, deploy_site: bool = True, project: str | None = None, runner: Runner | None = None, get: Getter | None = None,
            sleep: Callable[[float], None] | None = None, out: Callable[[str], None] = print) -> str | None:
    """Export, build, check and (unless deploy_site is False) publish and check the address. The address, when published.
    runner, get and sleep: programs, the web and waiting (tests give stand-ins)."""
    runner, get, sleep = runner or run, get or httpx2.get, sleep or time.sleep
    settings = load_settings()
    record = json.loads((folder / SITE_RECORD).read_text(encoding="utf-8")) if (folder / SITE_RECORD).exists() else {}
    if project and record.get("cloudflare_project") not in (None, project):
        raise PublishError(f"This notebook is published as the project {record['cloudflare_project']} ({record.get('url')}); --project would start another site.")
    project = record.get("cloudflare_project") or project or DEFAULT_PROJECT
    if deploy_site:
        check_login(runner)
    selection = read_selection(folder / "selection.json")

    out("1/4 Exporting the chosen recipes…")
    report = export_notebook(settings.database_path, media.media_root(settings.data_dir), selection, folder / "export")
    notebook = json.loads((folder / "export" / "notebook.json").read_text(encoding="utf-8"))
    out(f"    {len(report.recipes)} recipes, {report.files} pictures ({report.bytes / 1_000_000:.1f} MB). What becomes public:")
    for line in describe(notebook):
        out(line)
    for recipe_id, backup in report.drafts.items():
        demonstration = f"; a demonstration, {report.demonstrations[recipe_id]}" if recipe_id in report.demonstrations else ""
        check = f"; a classification check, {report.checks[recipe_id]}" if recipe_id in report.checks else ""
        out(f"    comparison page for {recipe_id}: {'with the import draft a backup kept' if backup else 'no draft was kept'}{demonstration}{check}")

    out("2/4 Building and checking the site…")
    site = build_site(folder, runner)
    out(f"    {sum(1 for p in site.rglob('*') if p.is_file())} files in {site}, checked.")
    if not deploy_site:
        out("Built, not published. To look at it: npm run preview:public (in frontend/), then http://localhost:4173")
        return None

    out(f"3/4 Uploading to Cloudflare Pages (project {project})…")
    url = deploy(site, project, runner)
    try:
        out(f"4/4 Checking {url}…")
        check_live(url, folder / "export", get, sleep)
    except PublishError as error:
        raise PublishError(f"The new version was uploaded, but checking it failed. {error}") from None
    record = {
        "cloudflare_project": project,
        "url": url,
        "last_published": {"at": datetime.now(UTC).isoformat(timespec="seconds"), "exported_at": notebook["exported_at"], "recipes": [r["id"] for r in notebook["recipes"]]},
    }
    (folder / SITE_RECORD).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out(f"Published: {url}")
    return url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export, build and publish the public, read-only notebook.")
    parser.add_argument("--add", type=int, nargs="+", default=[], metavar="ID", help="add these saved recipes to the selection first")
    parser.add_argument("--remove", type=int, nargs="+", default=[], metavar="ID", help="take these recipes out of the selection first")
    parser.add_argument("--list", action="store_true", help="list every recipe, whether it can be published and whether it is chosen")
    parser.add_argument("--no-deploy", action="store_true", help="export and build only")
    parser.add_argument("--project", help=f"the Cloudflare Pages project, at the first publication only (default: {DEFAULT_PROJECT})")
    parser.add_argument("--folder", type=Path, help="holds selection.json, export/ and site/ (default: <data folder>/public-notebook)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a console that cannot show a character shows "?" instead of failing
    settings = load_settings()
    folder = args.folder or settings.data_dir / "public-notebook"
    record_url = None
    if (folder / SITE_RECORD).exists():
        record_url = json.loads((folder / SITE_RECORD).read_text(encoding="utf-8")).get("url")
    try:
        if args.list:
            chosen = read_selection(folder / "selection.json") if (folder / "selection.json").exists() else None
            print("\n".join(list_candidates(settings.database_path, chosen)))
            return 0
        if args.add or args.remove:
            selection = change_selection(folder, settings.database_path, args.add, args.remove)
            print(f"Selection: {selection.recipes} (comparison pages: {selection.show_processing})")
        publish(folder, deploy_site=not args.no_deploy, project=args.project)
    except (ExportError, PublishError) as error:
        print(f"FAILED. {error}", file=sys.stderr)
        uploaded = isinstance(error, PublishError) and str(error).startswith("The new version was uploaded")
        if not uploaded:
            where = f" ({record_url})" if record_url else ""
            print(f"The public notebook{where} was not changed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
