"""Settings and the probe's offline analysis (no network).

Settings tests pass `_env_file` explicitly, so a developer's own .env cannot change their results.
"""

import sys

import pytest

from app.config import REPO_ROOT, Settings
from app.importers.instagram import CapturedPage
from scripts import probe_instagram


def test_data_dir_defaults_to_repo_data(monkeypatch):
    monkeypatch.delenv("RECIPES_DATA_DIR", raising=False)
    assert Settings(_env_file=None).data_dir == (REPO_ROOT / "data").resolve()


def test_data_dir_accepts_a_full_path(monkeypatch, tmp_path):
    monkeypatch.setenv("RECIPES_DATA_DIR", str(tmp_path))
    assert Settings(_env_file=None).data_dir == tmp_path.resolve()


def test_data_dir_rejects_a_relative_path(monkeypatch):
    # A relative path would depend on the current folder, e.g. backend/data, which git does not ignore.
    monkeypatch.setenv("RECIPES_DATA_DIR", "data")
    with pytest.raises(ValueError, match="full path"):
        Settings(_env_file=None)


def test_settings_are_read_from_a_dotenv_file_and_the_environment_wins(monkeypatch, tmp_path):
    from_file, from_environment = tmp_path / "from-file", tmp_path / "from-environment"
    env_file = tmp_path / ".env"
    env_file.write_text(f"RECIPES_DATA_DIR={from_file}\nANTHROPIC_API_KEY=ignored-here\n", encoding="utf-8")
    monkeypatch.delenv("RECIPES_DATA_DIR", raising=False)
    assert Settings(_env_file=env_file).data_dir == from_file.resolve()
    monkeypatch.setenv("RECIPES_DATA_DIR", str(from_environment))
    assert Settings(_env_file=env_file).data_dir == from_environment.resolve()


def make_run(tmp_path):
    run = tmp_path / "20261018-000000"
    folder = run / "Cm1mCdCpSzJ" / "http-embed"
    folder.mkdir(parents=True)
    html = '<html><head><meta property="og:description" content="baker on March 5, 2023: &quot;עוגה&quot;. "></head></html>'
    page = CapturedPage(method="http", requested_url="https://www.instagram.com/p/Cm1mCdCpSzJ/embed/captioned/", http_status=200, html=html)
    probe_instagram.save_capture(page, folder)
    return run


def test_analyze_saved_run_offline(tmp_path):
    run = make_run(tmp_path)
    (run / "Cm1mCdCpSzJ" / "browser-post").mkdir()  # interrupted capture: folder without capture.json
    probe_instagram.analyze_run(run)
    summary = (run / "summary.md").read_text(encoding="utf-8")
    assert "caption_incomplete" in summary
    assert (run / "Cm1mCdCpSzJ" / "http-embed" / "analysis.json").exists()
    assert not (run / "Cm1mCdCpSzJ" / "browser-post" / "analysis.json").exists()


def test_saved_pages_round_trip_byte_for_byte(tmp_path):
    # Text mode on Windows would turn "\n" into "\r\n"; saved pages must stay raw.
    html = "<html>line one\nline two\r\nline three</html>"
    probe_instagram.save_capture(CapturedPage(method="http", requested_url="u", html=html), tmp_path)
    assert probe_instagram.load_capture(tmp_path).html == html


def test_find_run_dir_accepts_a_run_id_and_rejects_other_folders(tmp_path):
    run = make_run(tmp_path)
    assert probe_instagram.find_run_dir(run.name, tmp_path) == run
    with pytest.raises(SystemExit):
        probe_instagram.find_run_dir(str(tmp_path), tmp_path)  # the parent folder, not a run


@pytest.fixture
def probe_offline(monkeypatch, tmp_path):
    """Run the probe's command line without the developer's settings and without any network."""
    monkeypatch.setattr(probe_instagram, "data_dir", lambda: tmp_path)

    async def no_live_capture(args, refs):
        raise AssertionError("this test must not reach the live capture")

    monkeypatch.setattr(probe_instagram, "run_capture", no_live_capture)
    return monkeypatch


@pytest.mark.parametrize(
    "argv",
    [
        ["--timeout", "0"],
        ["--delay", "0"],
        ["https://www.instagram.com/p/Cm1mCdCpSzJ/"] * 11,
        ["--strategies", ","],
        ["https://example.com/not-instagram"],
    ],
)
def test_probe_refuses_bad_or_unbounded_settings(probe_offline, argv):
    probe_offline.setattr(sys, "argv", ["probe_instagram", *argv])
    with pytest.raises(SystemExit) as refused:
        probe_instagram.main()
    assert refused.value.code == 2  # argparse's "usage error" code, not a crash or a settings error


def test_probe_reports_a_bad_setting_in_one_line(monkeypatch, capsys):
    monkeypatch.setenv("RECIPES_DATA_DIR", "data")
    monkeypatch.setattr(sys, "argv", ["probe_instagram", "--help"])
    with pytest.raises(SystemExit) as stopped:
        probe_instagram.main()
    assert stopped.value.code == "RECIPES_DATA_DIR must be a full path, such as D:/Backups/recipe-notebook (got 'data')"


def test_quoted_backslash_paths_in_dotenv_are_refused_with_a_hint(monkeypatch, tmp_path):
    # In .env, double quotes make python-dotenv turn "\r" in "D:\Backups\recipes" into a control character.
    env_file = tmp_path / ".env"
    env_file.write_text('RECIPES_DATA_DIR="' + "C:" + chr(92) + "Backups" + chr(92) + 'recipes"\n', encoding="utf-8")
    monkeypatch.delenv("RECIPES_DATA_DIR", raising=False)
    with pytest.raises(ValueError, match="forward slashes and no quotes"):
        Settings(_env_file=env_file)


def test_probe_loads_the_same_post_only_once(probe_offline, tmp_path):
    planned = []

    async def fake_run_capture(args, refs):  # stands in for the live capture: no network
        planned.extend(refs)
        return tmp_path

    probe_offline.setattr(probe_instagram, "run_capture", fake_run_capture)
    probe_offline.setattr(probe_instagram, "analyze_run", lambda run_dir: None)
    urls = ["https://www.instagram.com/p/Cm1mCdCpSzJ/", "https://www.instagram.com/reel/Cm1mCdCpSzJ/?igsh=x"]
    probe_offline.setattr(sys, "argv", ["probe_instagram", *urls])
    probe_instagram.main()
    assert [ref.shortcode for ref in planned] == ["Cm1mCdCpSzJ"]
