"""Reading a post for an import: which pages are loaded, in what order, and what is reported.

The two page loads are replaced by stand-ins that return pages shaped like the live captures
(tests/test_instagram_analysis.py), so these tests never reach Instagram.
"""

import threading

import pytest

from app.importers import instagram
from app.importers.instagram import CapturedPage, FetchOutcome, parse_instagram_url, retrieve_caption_blocking
from tests.test_instagram_analysis import (
    CAPTION,
    CODE,
    EMBED_TEXT,
    EMBED_URL,
    URL,
    embed_view,
    meta_page,
    page,
    post_data_doc,
    post_page,
)

REF = parse_instagram_url(URL)
UNAVAILABLE = "<html><head><title>Post isn't available • Instagram</title></head><body></body></html>"


@pytest.fixture
def pages(monkeypatch):
    """Set what each page load returns; records which addresses were loaded."""
    loaded: list[str] = []
    answers: dict[str, CapturedPage] = {}

    async def browser(url, **_):
        loaded.append(url)
        return answers["post"]

    async def http(url, **_):
        loaded.append(url)
        return answers["embed"]

    monkeypatch.setattr(instagram, "capture_with_browser", browser)
    monkeypatch.setattr(instagram, "capture_with_http", http)

    def set_pages(post: CapturedPage, embed: CapturedPage | None = None) -> list[str]:
        answers["post"] = post
        if embed is not None:
            answers["embed"] = embed
        return loaded

    return set_pages


def embed_page(html: str) -> CapturedPage:
    return page(html, method="http", requested_url=EMBED_URL)


def test_the_post_page_with_the_posts_own_data_is_enough(pages):
    loaded = pages(page(post_page(post_data_doc(coauthors=("friend",)))))
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.CAPTION_FOUND and result.complete
    assert result.caption == CAPTION and result.retrieved_from == "post_page"
    assert result.username == "baker" and result.coauthors == ["friend"]
    assert loaded == [URL]  # one page load, no fallback
    assert [attempt.page for attempt in result.attempts] == ["post_page"]


def test_the_embed_view_is_tried_once_when_the_post_page_shows_no_caption(pages):
    loaded = pages(page("<html><body>Instagram</body></html>"), embed_page(embed_view()))
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.CAPTION_FOUND and result.retrieved_from == "embed_view"
    assert result.caption == EMBED_TEXT
    assert loaded == [URL, EMBED_URL]
    assert [(a.page, a.outcome) for a in result.attempts] == [
        ("post_page", FetchOutcome.CAPTION_NOT_FOUND), ("embed_view", FetchOutcome.CAPTION_FOUND)
    ]


def test_without_a_browser_the_embed_view_still_works(pages):
    missing = CapturedPage(method="browser", requested_url=URL, error_kind="browser", error="Executable doesn't exist")
    pages(missing, embed_page(embed_view()))
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.CAPTION_FOUND and result.retrieved_from == "embed_view"
    assert result.attempts[0].error == "Executable doesn't exist"


@pytest.mark.parametrize(
    ("post", "outcome"),
    [
        (page(UNAVAILABLE), FetchOutcome.UNAVAILABLE),
        (page("<html><body>Please wait a few minutes before you try again.</body></html>"), FetchOutcome.RATE_LIMITED),
        (page(post_page(post_data_doc(caption=None))), FetchOutcome.NO_CAPTION),
    ],
)
def test_what_instagram_says_about_the_post_is_final(pages, post, outcome):
    loaded = pages(post)
    result = retrieve_caption_blocking(REF)
    assert result.outcome is outcome and result.caption is None
    assert loaded == [URL]  # asking another page would not change the answer (and must not, when rate limited)


def test_a_preview_alone_is_reported_incomplete_with_its_text(pages):
    preview = "עוגת גבינה פירורים 🍰 מצרכים לבצק: 200 גרם קמח…"
    pages(page(meta_page(preview)), embed_page("<html><body>Instagram</body></html>"))
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.CAPTION_INCOMPLETE and not result.complete
    assert result.caption == preview and result.retrieved_from == "post_page"


def test_the_complete_caption_from_the_embed_view_beats_a_preview_on_the_post_page(pages):
    pages(page(meta_page("קצר")), embed_page(embed_view()))
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.CAPTION_FOUND and result.caption == EMBED_TEXT


def test_when_neither_page_has_the_caption_the_more_telling_reason_is_given(pages):
    login = page('<html><body><input name="password"></body></html>',
                 final_url="https://www.instagram.com/accounts/login/")
    timeout = CapturedPage(method="http", requested_url=EMBED_URL, error_kind="timeout", error="Timed out")
    pages(login, timeout)
    result = retrieve_caption_blocking(REF)
    assert result.outcome is FetchOutcome.LOGIN_REQUIRED and result.caption is None
    assert [a.outcome for a in result.attempts] == [FetchOutcome.LOGIN_REQUIRED, FetchOutcome.TIMEOUT]


def test_reading_works_from_a_worker_thread_like_an_api_request(pages):
    # FastAPI runs the import in a worker thread; the read gets an event loop of its own there.
    pages(page(post_page(post_data_doc())))
    results = []
    worker = threading.Thread(target=lambda: results.append(retrieve_caption_blocking(REF)))
    worker.start()
    worker.join(timeout=30)
    assert [result.outcome for result in results] == [FetchOutcome.CAPTION_FOUND]
    assert CODE in results[0].url
