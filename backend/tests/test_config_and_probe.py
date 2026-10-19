"""The data-folder setting and the probe's offline analysis (no network)."""

import sys

import pytest

from app.config import REPO_ROOT, data_dir
from app.importers.instagram import CapturedPage
from scripts import probe_instagram


def test_data_dir_defaults_to_repo_data(monkeypatch):
    monkeypatch.delenv("RECIPES_DATA_DIR", raising=False)
    assert data_dir() == (REPO_ROOT / "data").resolve()


def test_data_dir_accepts_a_full_path(monkeypatch, tmp_path):
    monkeypatch.setenv("RECIPES_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path.resolve()


def test_data_dir_rejects_a_relative_path(monkeypatch):
    # A relative path would depend on the current folder, e.g. backend/data, which git does not ignore.
    monkeypatch.setenv("RECIPES_DATA_DIR", "data")
    with pytest.raises(ValueError, match="full path"):
        data_dir()


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
def test_probe_refuses_bad_or_unbounded_settings(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["probe_instagram", *argv])
    with pytest.raises(SystemExit):
        probe_instagram.main()


def test_probe_loads_the_same_post_only_once(monkeypatch, tmp_path):
    planned = []

    async def fake_run_capture(args, refs):  # stands in for the live capture: no network
        planned.extend(refs)
        return tmp_path

    monkeypatch.setattr(probe_instagram, "run_capture", fake_run_capture)
    monkeypatch.setattr(probe_instagram, "analyze_run", lambda run_dir: None)
    urls = ["https://www.instagram.com/p/Cm1mCdCpSzJ/", "https://www.instagram.com/reel/Cm1mCdCpSzJ/?igsh=x"]
    monkeypatch.setattr(sys, "argv", ["probe_instagram", *urls])
    probe_instagram.main()
    assert [ref.shortcode for ref in planned] == ["Cm1mCdCpSzJ"]
