"""Bounded live probe for the Instagram importer (milestone 1).

Run from the backend/ folder:

    uv run python -m scripts.probe_instagram                  # the three URLs from the brief
    uv run python -m scripts.probe_instagram URL [URL ...]    # other public posts
    uv run python -m scripts.probe_instagram --headed         # watch the browser window
    uv run python -m scripts.probe_instagram --analyze PATH   # re-analyze a saved run offline

Each URL is loaded once per strategy, one page at a time, with a pause in
between: at most len(urls) x len(strategies) page loads per run. The run stops
at the first sign of rate limiting or a login wall. Raw artifacts
(HTML, JSON responses, screenshots) are saved under data/instagram-probe/<run-id>/
(git-ignored), so the analysis can be repeated offline without contacting
Instagram again.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from app.config import data_dir
from app.importers.instagram import (
    CaptionAnalysis,
    CaptionCandidate,
    CapturedPage,
    FetchOutcome,
    InstagramRef,
    InvalidInstagramUrl,
    analyze_capture,
    capture_with_browser,
    capture_with_http,
    parse_instagram_url,
)

BRIEF_URLS = [
    "https://www.instagram.com/p/Cm1mCdCpSzJ/",
    "https://www.instagram.com/p/DPbKEn-CnUt/",
    "https://www.instagram.com/p/DANUmOOIcRM/",
]
STRATEGIES = {
    "browser-post": "Playwright Chromium loads the normal post page, logged out",
    "browser-embed": "Playwright Chromium loads the public embed view",
    "http-post": "Plain HTTP GET of the post page (no JavaScript)",
    "http-embed": "Plain HTTP GET of the embed view (no JavaScript)",
}


# --- Capture (live) ----------------------------------------------------------


async def capture(strategy: str, ref: InstagramRef, args: argparse.Namespace, folder: Path) -> CapturedPage:
    url = ref.embed_url if strategy.endswith("-embed") else ref.canonical_url
    if strategy.startswith("browser-"):
        return await capture_with_browser(
            url,
            headless=not args.headed,
            channel=args.channel,
            timeout_s=args.timeout,
            screenshot_path=str(folder / "screenshot.png"),
        )
    return await capture_with_http(url, timeout_s=args.timeout)


async def run_capture(args: argparse.Namespace, refs: list[InstagramRef]) -> Path:
    run_dir = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    plan = [(ref, strategy) for ref in refs for strategy in args.strategies]
    print(f"Probe run {run_dir}")
    print(f"{len(refs)} post(s) x {len(args.strategies)} strategies = at most {len(plan)} page loads, {args.delay:g}s apart\n")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    stopped_early = None
    for count, (ref, strategy) in enumerate(plan, start=1):
        if count > 1:
            await asyncio.sleep(args.delay)
        folder = run_dir / ref.shortcode / strategy
        folder.mkdir(parents=True, exist_ok=True)
        print(f"[{count}/{len(plan)}] {ref.shortcode} {strategy} ...", flush=True)
        captured = await capture(strategy, ref, args, folder)
        save_capture(captured, folder)
        outcome = analyze_capture(captured, ref.shortcode).outcome
        note = f", error={captured.error_kind}: {captured.error}" if captured.error else ""
        print(f"    HTTP {captured.http_status}, {captured.elapsed_ms} ms -> {outcome.value}{note}")
        # Instagram is pushing back: more requests now would only make it worse.
        if outcome in (FetchOutcome.RATE_LIMITED, FetchOutcome.LOGIN_REQUIRED):
            stopped_early = f"{outcome.value} at {ref.shortcode}/{strategy}"
            print(f"\nStopping early ({stopped_early}); remaining page loads skipped.")
            break

    run_info = {
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "playwright": version("playwright"),
        "httpx": version("httpx"),
        "headless": not args.headed,
        "channel": args.channel or "bundled chromium",
        "timeout_s": args.timeout,
        "delay_s": args.delay,
        "urls": [ref.canonical_url for ref in refs],
        "strategies": args.strategies,
        "stopped_early": stopped_early,
    }
    write_json(run_dir / "run.json", run_info)
    return run_dir


def save_capture(captured: CapturedPage, folder: Path) -> None:
    # Bytes, not text mode: text mode on Windows would turn every "\n" into "\r\n".
    (folder / "page.html").write_bytes(captured.html.encode("utf-8"))
    write_json(folder / "capture.json", captured.model_dump(mode="json", exclude={"html"}))


def load_capture(folder: Path) -> CapturedPage:
    data = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
    data["html"] = (folder / "page.html").read_bytes().decode("utf-8")
    return CapturedPage.model_validate(data)


# --- Analysis (offline) --------------------------------------------------------


def find_run_dir(value: str, out: Path) -> Path:
    """Accept a run folder path, or just its run ID (looked up inside --out)."""
    path = Path(value)
    if not path.exists() and (out / value).is_dir():
        path = out / value
    if not any(path.glob("*/*/capture.json")):
        raise SystemExit(
            f"{path} is not a probe run folder: expected <shortcode>/<strategy>/capture.json inside it.\n"
            f"Runs are saved in {out}; pass one run's folder (or its ID, such as 20261018-135240)."
        )
    return path


def analyze_run(run_dir: Path) -> None:
    run_info = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").exists() else {}
    rows: list[dict] = []
    details: list[str] = []

    for post_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        shortcode = post_dir.name
        results: dict[str, tuple[CapturedPage, CaptionAnalysis]] = {}
        for strategy in [s for s in STRATEGIES if (post_dir / s).is_dir()]:
            folder = post_dir / strategy
            if not (folder / "capture.json").exists():
                print(f"Skipping {shortcode}/{strategy}: no capture.json (interrupted run?)")
                continue
            captured = load_capture(folder)
            analysis = analyze_capture(captured, shortcode)
            write_json(folder / "analysis.json", analysis.model_dump(mode="json"))
            results[strategy] = (captured, analysis)
        if not results:
            continue

        reference = reference_caption([analysis for _, analysis in results.values()])
        details.append(f"### {shortcode}\n")
        details.append(
            f"Reference (complete) caption: {len(reference.text)} characters from `{reference.source}`\n"
            if reference
            else "No caption from the post's own data was found by any strategy, so completeness cannot be confirmed.\n"
        )
        for strategy, (captured, analysis) in results.items():
            best = analysis.best
            rows.append(
                {
                    "post": shortcode,
                    "strategy": strategy,
                    "http": captured.http_status,
                    "redirected_to": captured.final_url if captured.final_url != captured.requested_url else None,
                    "outcome": analysis.outcome.value,
                    "best_source": best.source.value if best else None,
                    "chars": len(best.text) if best else 0,
                    "vs_reference": compare(best, reference),
                    "login_redirect": analysis.signals.login_redirect,
                    "login_form": analysis.signals.login_form,
                    "media_json": analysis.signals.media_json_found,
                    "title": analysis.signals.title,
                    "elapsed_ms": captured.elapsed_ms,
                    "error": captured.error,
                }
            )
            details.append(f"**{strategy}** → `{analysis.outcome.value}`")
            for candidate in analysis.candidates:
                author = candidate.username or "unknown author"
                if candidate.coauthors:
                    author += f" with {', '.join(candidate.coauthors)}"
                details.append(
                    f"- `{candidate.source}` ({author}): {len(candidate.text)} chars, truncated={candidate.truncated}, "
                    f"vs reference: {compare(candidate, reference)} — {preview(candidate.text)}"
                )
            if not analysis.candidates:
                details.append("- no caption candidates")
            details.append("")

    write_json(run_dir / "summary.json", {"run": run_info, "rows": rows})
    (run_dir / "summary.md").write_text(render_markdown(run_dir, run_info, rows, details), encoding="utf-8")
    print_table(rows)
    print(f"\nDetails: {run_dir / 'summary.md'}")


def reference_caption(analyses: list[CaptionAnalysis]) -> CaptionCandidate | None:
    """The longest caption that came from the post's own data (truncated=False)."""
    complete = [c for analysis in analyses for c in analysis.candidates if c.truncated is False]
    return max(complete, key=lambda c: len(c.text), default=None)


def compare(candidate: CaptionCandidate | None, reference: CaptionCandidate | None) -> str:
    if candidate is None:
        return "-"
    if reference is None:
        return "no reference"
    text, full = " ".join(candidate.text.split()), " ".join(reference.text.split())
    if text == full:
        return "identical"
    stem = text.rstrip(" .…").removesuffix("more").rstrip(" .…")
    if full.startswith(stem):
        return f"prefix ({len(stem)}/{len(full)} chars)"
    return "different"


def preview(text: str, head: int = 70, tail: int = 50) -> str:
    flat = " ⏎ ".join(line.strip() for line in text.strip().splitlines() if line.strip())
    return flat if len(flat) <= head + tail + 5 else f"{flat[:head]} … {flat[-tail:]}"


def render_markdown(run_dir: Path, run_info: dict, rows: list[dict], details: list[str]) -> str:
    lines = [
        f"# Instagram probe run {run_dir.name}",
        "",
        "Generated by `scripts/probe_instagram.py`. Raw artifacts are next to this file.",
        "",
        "## Environment",
        "",
        *[f"- {key}: {value}" for key, value in run_info.items()],
        "",
        "## Strategies",
        "",
        *[f"- `{name}`: {description}" for name, description in STRATEGIES.items()],
        "",
        "## Results",
        "",
        "| Post | Strategy | HTTP | Outcome | Best source | Chars | vs reference | Login redirect | Login form | Post JSON |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['post']} | {row['strategy']} | {row['http']} | {row['outcome']} | {row['best_source'] or '-'} "
            f"| {row['chars']} | {row['vs_reference']} | {row['login_redirect']} | {row['login_form']} | {row['media_json']} |"
        )
    lines += ["", "## Caption candidates per post", "", *details]
    return "\n".join(lines) + "\n"


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No captures to show.")
        return
    columns = ["post", "strategy", "http", "outcome", "best_source", "chars", "vs_reference", "login_redirect", "login_form"]
    widths = {col: max(len(col), *(len(str(row[col])) for row in rows)) for col in columns}
    print("\n" + "  ".join(col.ljust(widths[col]) for col in columns))
    for row in rows:
        print("  ".join(str(row[col]).ljust(widths[col]) for col in columns))


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Entry point ----------------------------------------------------------------


MAX_URLS = 10  # keeps a run bounded; this is a probe, not a collector


class HelpFormatter(argparse.RawDescriptionHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
    """Keep the module docstring's layout and show each option's default."""


def bounded_float(low: float, high: float):
    def parse(text: str) -> float:
        value = float(text)
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"must be between {low:g} and {high:g}")
        return value

    return parse


def main() -> None:
    # Captions are Hebrew; make console output UTF-8 even when it is redirected on Windows.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        default_out = data_dir() / "instagram-probe"
    except ValueError as exc:
        sys.exit(str(exc))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=HelpFormatter)
    parser.add_argument("urls", nargs="*", help=f"Instagram post/Reel URLs, at most {MAX_URLS} (default: the three from the brief)")
    parser.add_argument(
        "--strategies",
        type=lambda value: [s.strip() for s in value.split(",") if s.strip()],
        default=list(STRATEGIES),
        help=f"Comma-separated subset of: {', '.join(STRATEGIES)}",
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless")
    parser.add_argument("--channel", help='Use an installed browser instead of bundled Chromium, e.g. "msedge"')
    parser.add_argument("--timeout", type=bounded_float(1, 120), default=30.0, help="Navigation timeout per page, in seconds")
    parser.add_argument("--delay", type=bounded_float(3, 600), default=10.0, help="Pause between page loads, in seconds")
    parser.add_argument("--out", default=str(default_out), help="Folder for probe runs")
    parser.add_argument("--analyze", metavar="RUN", help="Only re-analyze a saved run: its folder or run ID (no network)")
    args = parser.parse_args()

    unknown = [s for s in args.strategies if s not in STRATEGIES]
    if unknown:
        parser.error(f"Unknown strategies: {', '.join(unknown)}")
    if not args.strategies:
        parser.error("No strategies given.")
    if len(args.urls) > MAX_URLS:
        parser.error(f"At most {MAX_URLS} URLs per run.")

    if args.analyze:
        run_dir = find_run_dir(args.analyze, Path(args.out))
    else:
        try:
            refs = [parse_instagram_url(url) for url in (args.urls or BRIEF_URLS)]
        except InvalidInstagramUrl as exc:
            parser.error(str(exc))
        # The same post pasted twice (e.g. as /p/ and /reel/) is loaded once.
        refs = list({ref.shortcode: ref for ref in refs}.values())
        run_dir = asyncio.run(run_capture(args, refs))
    analyze_run(run_dir)


if __name__ == "__main__":
    main()
