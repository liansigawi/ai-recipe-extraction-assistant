"""The one command that updates the public notebook (scripts/publish_public.py): export, build and check,
publish, check the address. npm, Wrangler and the public address are stand-ins: no build tools run and
nothing is sent to Cloudflare. What matters most: a step that fails leaves the published version alone."""

import json
import shutil
import subprocess
from pathlib import Path

import httpx2
import pytest

from scripts import publish_public
from scripts.export_public import ExportError
from scripts.publish_public import PublishError, change_selection, check_site, main, publish
from tests.test_export_public import JPEG, ORIGIN, attach, new_recipe


def done(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, out, err)


class Tools:
    """npm and Wrangler as the command calls them. The build copies the export beside a page, like Vite;
    a deployment keeps a copy of what was uploaded, which the stand-in address then serves."""

    def __init__(self, folder: Path, logged_in: bool = True, fail: str | None = None, extra: dict[str, bytes] | None = None):
        self.folder, self.logged_in, self.fail, self.extra = folder, logged_in, fail, extra or {}
        self.projects: list[str] = []
        self.calls: list[list[str]] = []
        self.live = folder.parent / "live"  # what the public address serves

    def __call__(self, command: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess[str]:
        args = command[1:]
        self.calls.append(args)
        if args[:2] == ["run", "build:public"]:
            if self.fail == "build":
                return done(1, err="src/App.tsx(3,1): error TS2304: Cannot find name 'x'.")
            out = Path(args[args.index("--outDir") + 1])
            shutil.copytree(Path(env["PUBLIC_NOTEBOOK_FOLDER"]) / "export", out)
            (out / "assets").mkdir()
            (out / "assets" / "index-abc.js").write_text("console.log('notebook')", encoding="utf-8")
            (out / "index.html").write_text('<div id="root"></div><script src="./assets/index-abc.js"></script>', encoding="utf-8")
            for name, content in self.extra.items():
                (out / name).write_bytes(content)
            return done(0, "built")
        wrangler = args[2:]
        if wrangler == ["whoami"]:
            return done(0, "You are logged in with an OAuth Token." if self.logged_in else "You are not authenticated. Please run `wrangler login`.")
        if wrangler[:3] == ["pages", "project", "list"]:
            return done(0, json.dumps([{"Project Name": name, "Project Domains": f"{name}-x1.pages.dev"} for name in self.projects]))
        if wrangler[:3] == ["pages", "project", "create"]:
            self.projects.append(wrangler[3])
            return done(0, "Successfully created the project")
        if wrangler[:2] == ["pages", "deploy"]:
            if self.fail == "deploy":
                return done(1, err="Authentication error [code: 10000]")
            if self.live.exists():
                shutil.rmtree(self.live)
            shutil.copytree(wrangler[2], self.live)
            return done(0, "Deployment complete! Take a peek over at https://1a2b3c4d.recipe-notebook-x1.pages.dev")
        raise AssertionError(f"unexpected command {args}")

    def get(self, url: str, **kwargs) -> httpx2.Response:
        path = url.split(".pages.dev/", 1)[1] or "index.html"
        file = self.live / path
        return httpx2.Response(200, content=file.read_bytes()) if file.is_file() else httpx2.Response(404)

    def ran(self, *start: str) -> bool:
        return any(call[: len(start)] == list(start) for call in self.calls)


@pytest.fixture
def folder(client, data_dir, monkeypatch) -> Path:
    """A notebook with a saved recipe that has a page's picture, and a draft; the selection names the recipe."""
    monkeypatch.setattr(publish_public, "tool", lambda name: name)  # npm and npx need not be installed
    cake = new_recipe(client, "עוגת תפוזים")
    attach(client, data_dir, cake["id"], kind="image", file=JPEG, origin="website", post_url="https://example.com/cake")
    client.post("/api/imports/text", json={"text": "עוד מתכון\nכוס קמח", "use_model": False}, headers=ORIGIN)
    folder = data_dir / "public-notebook"
    folder.mkdir()
    (folder / "selection.json").write_text(json.dumps({"recipes": [cake["id"]]}), encoding="utf-8")
    return folder


def recipe_ids(client, status: str) -> list[int]:
    return [r["id"] for r in client.get("/api/recipes").json() if r["status"] == status and not r["is_sample"]]


def test_one_command_exports_builds_publishes_and_checks_the_address(folder, client):
    tools = Tools(folder)
    lines: list[str] = []
    url = publish(folder, runner=tools, get=tools.get, sleep=lambda s: None, out=lines.append)

    assert url == "https://recipe-notebook-x1.pages.dev"
    assert tools.ran("--no-install", "wrangler", "pages", "project", "create", "recipe-notebook", "--production-branch", "main")
    deploy = next(call for call in tools.calls if call[2:4] == ["pages", "deploy"])
    assert deploy[4] == str(folder / "site") and deploy[deploy.index("--branch") + 1] == "main"
    assert any("עוגת תפוזים" in line and "picture from the website" in line for line in lines)  # what becomes public
    record = json.loads((folder / "site.json").read_text(encoding="utf-8"))
    assert record["cloudflare_project"] == "recipe-notebook" and record["url"] == url
    assert record["last_published"]["recipes"] == recipe_ids(client, "saved")
    assert not (folder / "site.partial").exists()

    # The next publication goes to the same project and address, with no new project.
    tools.calls.clear()
    assert publish(folder, runner=tools, get=tools.get, sleep=lambda s: None, out=lines.append) == url
    assert not tools.ran("--no-install", "wrangler", "pages", "project", "create")


def test_without_a_cloudflare_login_nothing_is_exported_or_built(folder):
    tools = Tools(folder, logged_in=False)
    with pytest.raises(PublishError, match="npx wrangler login"):
        publish(folder, runner=tools, get=tools.get, out=lambda line: None)
    assert tools.calls == [["--no-install", "wrangler", "whoami"]]
    assert not (folder / "export").exists()


def test_a_failed_export_stops_before_the_build(folder, client):
    (folder / "selection.json").write_text(json.dumps({"recipes": recipe_ids(client, "draft")}), encoding="utf-8")
    tools = Tools(folder)
    with pytest.raises(ExportError, match="draft"):
        publish(folder, runner=tools, get=tools.get, out=lambda line: None)
    assert not tools.ran("run", "build:public") and not tools.ran("--no-install", "wrangler", "pages", "deploy")


def test_a_failed_build_keeps_the_last_build_and_publishes_nothing(folder):
    (folder / "site").mkdir()
    (folder / "site" / "index.html").write_text("the last good build", encoding="utf-8")
    tools = Tools(folder, fail="build")
    with pytest.raises(PublishError, match="TS2304"):
        publish(folder, runner=tools, get=tools.get, out=lambda line: None)
    assert (folder / "site" / "index.html").read_text(encoding="utf-8") == "the last good build"
    assert not (folder / "site.partial").exists()
    assert not tools.ran("--no-install", "wrangler", "pages", "deploy")


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"recipes.db": b"SQLite format 3"}, "a file that does not belong in it: recipes.db"),
        ({"notes.txt": b"x"}, "a file that does not belong in it: notes.txt"),
    ],
)
def test_a_build_with_files_that_do_not_belong_is_not_published(folder, extra, message):
    tools = Tools(folder, extra=extra)
    with pytest.raises(PublishError, match=message):
        publish(folder, runner=tools, get=tools.get, out=lambda line: None)
    assert not tools.ran("--no-install", "wrangler", "pages", "deploy")


def test_a_key_or_a_local_folder_in_any_file_stops_the_publication(folder, monkeypatch):
    key = "sk-ant-test-1234567890"
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    tools = Tools(folder)
    publish(folder, deploy_site=False, runner=tools, out=lambda line: None)
    site = folder / "site"
    (site / "assets" / "index-abc.js").write_text(f"const k = '{key}'", encoding="utf-8")
    with pytest.raises(PublishError, match="contains an API key") as error:
        check_site(site, folder / "export")
    assert key not in str(error.value)  # the report never repeats the key
    (site / "assets" / "index-abc.js").write_text(f"const p = '{Path.home().as_posix()}'", encoding="utf-8")
    with pytest.raises(PublishError, match="contains a folder of this computer"):
        check_site(site, folder / "export")
    next((site / "media").iterdir()).unlink()
    with pytest.raises(PublishError, match="a picture a recipe names is missing"):
        check_site(site, folder / "export")


def test_a_failed_upload_leaves_the_address_as_it_was(folder, capsys, monkeypatch):
    tools = Tools(folder)
    url = publish(folder, runner=tools, get=tools.get, sleep=lambda s: None, out=lambda line: None)
    before = (folder / "site.json").read_text(encoding="utf-8")
    live = (tools.live / "notebook.json").read_text(encoding="utf-8")
    tools.fail = "deploy"
    monkeypatch.setattr(publish_public, "run", tools)
    monkeypatch.setattr(publish_public.httpx2, "get", tools.get)
    assert main([]) == 1
    error = capsys.readouterr().err
    assert "The upload to Cloudflare failed" in error and f"The public notebook ({url}) was not changed." in error
    assert (folder / "site.json").read_text(encoding="utf-8") == before
    assert (tools.live / "notebook.json").read_text(encoding="utf-8") == live


def test_an_address_still_showing_the_old_version_is_reported(folder, monkeypatch):
    tools = Tools(folder)

    def old_version(url: str, **kwargs) -> httpx2.Response:
        if url.endswith("notebook.json"):
            return httpx2.Response(200, json={"exported_at": "2026-01-01T00:00:00Z"})
        return tools.get(url, **kwargs)

    monkeypatch.setattr(publish_public, "LIVE_WAIT_S", 0)
    with pytest.raises(PublishError, match="new version was uploaded, but checking it failed.*does not show the new version yet.*2026-01-01"):
        publish(folder, runner=tools, get=old_version, sleep=lambda s: None, out=lambda line: None)
    assert not (folder / "site.json").exists()  # not recorded as published


def test_adding_and_removing_recipes_in_the_selection(folder, client, data_dir):
    database = data_dir / "recipes.db"
    [cake] = recipe_ids(client, "saved")
    lemon = new_recipe(client, "עוגת לימון")["id"]
    plum = new_recipe(client, "עוגת שזיפים")["id"]
    assert change_selection(folder, database, add=[lemon, plum], remove=[]).recipes == [cake, lemon, plum]
    assert change_selection(folder, database, add=[], remove=[plum]).recipes == [cake, lemon]
    # One refused number changes nothing, not even the others.
    with pytest.raises(ExportError, match="a draft that has not been reviewed"):
        change_selection(folder, database, add=[plum, recipe_ids(client, "draft")[0]], remove=[])
    assert json.loads((folder / "selection.json").read_text(encoding="utf-8"))["recipes"] == [cake, lemon]
    sample = next(r["id"] for r in client.get("/api/recipes").json() if r["is_sample"])
    with pytest.raises(ExportError, match="an invented sample recipe"):
        change_selection(folder, database, add=[sample], remove=[])
    with pytest.raises(ExportError, match="no recipe 999"):
        change_selection(folder, database, add=[999], remove=[])
    (folder / "selection.json").write_text(json.dumps({"recipes": [cake, lemon], "show_processing": [lemon]}), encoding="utf-8")
    assert change_selection(folder, database, add=[], remove=[lemon]).model_dump()["show_processing"] == []
    assert json.loads((folder / "selection.json").read_text(encoding="utf-8"))["recipes"] == [cake]


def test_the_list_shows_what_is_chosen_and_what_the_notebook_no_longer_has(folder, client, capsys):
    [cake] = recipe_ids(client, "saved")
    (folder / "selection.json").write_text(json.dumps({"recipes": [cake, 999], "show_processing": [cake]}), encoding="utf-8")
    assert main(["--list"]) == 0
    listing = capsys.readouterr().out
    assert any(line.startswith(f"{cake:>4}  yes") and "yes, compared" in line for line in listing.splitlines())
    assert "no longer has: 999" in listing
