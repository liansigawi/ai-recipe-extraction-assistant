"""Retrieve the caption of a public Instagram post or Reel.

Fetching is deliberately separate from recipe interpretation. This module only
answers: "what does the caption say, and do we believe we have all of it?"
Turning the caption into a structured recipe is a later, separate step.

Ground rules (see docs/brief.md and docs/instagram-feasibility.md):
- One user-supplied URL at a time. No bulk collection.
- No login automation, no forged-header calls to private endpoints, and no
  bot-detection evasion. A login wall, rate limit or unavailable post is
  reported as such, and the user falls back to pasting the caption or
  uploading screenshots.

The work is split in two so it can be tested without the network:
1. capture_with_browser / capture_with_http load a page and keep the raw
   material (HTML and the JSON responses the page itself received).
2. analyze_capture is a pure function that looks for the caption in that
   material and decides what happened.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import re
import sys
import time
from collections.abc import Iterator
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx2
from bs4 import BeautifulSoup, Tag
from bs4.element import PreformattedString
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Response, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------


class InvalidInstagramUrl(ValueError):
    """The text is not a link to a single Instagram post or Reel."""


class InstagramRef(BaseModel):
    """A normalized reference to one post or Reel."""

    shortcode: str
    kind: Literal["p", "reel"]

    @property
    def canonical_url(self) -> str:
        return f"https://www.instagram.com/{self.kind}/{self.shortcode}/"

    @property
    def embed_url(self) -> str:
        # Instagram's public embed view: the same page websites show in an
        # iframe when they embed a post. Creators can disable embedding.
        return f"https://www.instagram.com/p/{self.shortcode}/embed/captioned/"


_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am", "www.instagr.am"}
_KINDS = {"p": "p", "tv": "p", "reel": "reel", "reels": "reel"}
_NON_POST_SECTIONS = {"stories", "explore", "accounts", "direct", "about", "legal"}
_SHORTCODE_RE = re.compile(r"[A-Za-z0-9_-]{5,64}")
_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://")


def parse_instagram_url(text: str) -> InstagramRef:
    """Accept the URL shapes people actually paste and return a canonical reference.

    Supported: /p/<code>/, /reel/<code>/, /reels/<code>/, /tv/<code>/, the same
    paths after a username (/<user>/p/<code>/), with or without www/m, and with
    tracking query strings such as ?igsh=... or ?img_index=1.
    """
    raw = text.strip()
    if not raw:
        raise InvalidInstagramUrl("The URL is empty.")
    if not _SCHEME_RE.match(raw):
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
    except ValueError:  # e.g. malformed brackets or characters in the host
        raise InvalidInstagramUrl("This is not an instagram.com link.") from None
    if parts.scheme not in ("http", "https") or host not in _HOSTS:
        raise InvalidInstagramUrl("This is not an instagram.com link.")

    segments = [segment for segment in parts.path.split("/") if segment]
    if segments and segments[0].lower() == "share":
        # /share/... links only redirect to the real post address.
        raise InvalidInstagramUrl(
            "Share links (instagram.com/share/...) are not supported yet. "
            "Open the link in your browser and copy the post's address instead."
        )
    if segments and segments[0].lower() in _NON_POST_SECTIONS:
        raise InvalidInstagramUrl("Only links to a single post or Reel are supported.")
    # The post type is the first path segment, or the second when a username comes first.
    for index in (0, 1):
        if index + 1 < len(segments) and segments[index].lower() in _KINDS:
            shortcode = segments[index + 1]
            # /reels/audio/<id>/ is a sound page, not a post.
            if _SHORTCODE_RE.fullmatch(shortcode) and shortcode.lower() != "audio":
                return InstagramRef(shortcode=shortcode, kind=_KINDS[segments[index].lower()])
            break
    raise InvalidInstagramUrl("Only links to a single post or Reel are supported.")


# ---------------------------------------------------------------------------
# Captured page: the raw material from one page load
# ---------------------------------------------------------------------------


class NetworkJson(BaseModel):
    """A JSON response that the page itself requested while loading."""

    url: str
    status: int
    body: Any


class CapturedPage(BaseModel):
    """Everything kept from one page load, so analysis can be repeated offline."""

    method: Literal["browser", "http"]
    requested_url: str
    final_url: str | None = None
    http_status: int | None = None
    html: str = ""
    network_json: list[NetworkJson] = Field(default_factory=list)
    user_agent: str | None = None
    browser_version: str | None = None
    elapsed_ms: int = 0
    error_kind: Literal["timeout", "network", "browser"] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Analysis results
# ---------------------------------------------------------------------------


class CaptionSource(StrEnum):
    MEDIA_JSON_EMBEDDED = "media_json_embedded"  # post data embedded in the page HTML
    MEDIA_JSON_NETWORK = "media_json_network"  # post data the page fetched while loading
    EMBED_PAGE = "embed_page"  # caption block rendered by the public embed view
    META_DESCRIPTION = "meta_description"  # og:description / description preview


class PostPerson(BaseModel):
    """An account as the post's data names it: the username, and the display name when given."""

    username: str
    full_name: str | None = None


class PostMediaItem(BaseModel):
    """One picture or video of a post, in the post's order (a carousel has up to 20)."""

    index: int  # its place in the post, from 0
    kind: Literal["image", "video"]
    image_url: str | None = None  # the picture; for a video, its poster frame
    video_urls: list[str] = Field(default_factory=list)  # a video's files, the best first
    width: int | None = None
    height: int | None = None


class CaptionCandidate(BaseModel):
    source: CaptionSource
    text: str
    author: PostPerson | None = None  # the account that posted it
    coauthors: list[PostPerson] = Field(default_factory=list)  # collaboration posts (seen live)
    media: list[PostMediaItem] = Field(default_factory=list)  # only from the post's own data
    # True: visibly cut off. False: taken from the post's own data, so complete.
    # None: no evidence either way.
    truncated: bool | None = None


class FetchOutcome(StrEnum):
    # The post was read:
    CAPTION_FOUND = "caption_found"  # caption believed complete
    CAPTION_INCOMPLETE = "caption_incomplete"  # caption found but cut off or unverifiable
    NO_CAPTION = "no_caption"  # the post exists and has no caption text
    # The post could not be read:
    LOGIN_REQUIRED = "login_required"  # login wall, gated post, or access refused (HTTP 401/403)
    UNAVAILABLE = "unavailable"  # deleted, private, or not shown
    RATE_LIMITED = "rate_limited"
    CAPTION_NOT_FOUND = "caption_not_found"  # page loaded, but no caption data was recognized
    TIMEOUT = "timeout"
    ERROR = "error"

    @property
    def post_was_read(self) -> bool:
        return self in (FetchOutcome.CAPTION_FOUND, FetchOutcome.CAPTION_INCOMPLETE, FetchOutcome.NO_CAPTION)


class PageSignals(BaseModel):
    """Observations used to explain the outcome; also useful in the probe report."""

    title: str | None = None
    route: str | None = None  # Instagram's internal page route, e.g. comet.igweb.PolarisErrorRoute
    login_redirect: bool = False
    login_form: bool = False
    unavailable_message: bool = False
    rate_limit_message: bool = False
    media_json_found: bool = False
    media_caption_empty: bool = False
    # The post exists but Instagram only shows it to logged-in users (for example age-restricted).
    gated_for_logged_out: bool = False
    # The page names a different post (og:url, canonical link, embed permalink).
    other_post_shown: bool = False


class CaptionAnalysis(BaseModel):
    outcome: FetchOutcome
    best: CaptionCandidate | None = None
    candidates: list[CaptionCandidate] = Field(default_factory=list)
    signals: PageSignals


# ---------------------------------------------------------------------------
# Analysis: pure functions over a CapturedPage
# ---------------------------------------------------------------------------

_UNAVAILABLE_PHRASES = (
    "sorry, this page isn't available",
    "the link you followed may be broken",
    "this content isn't available",
    "this content is no longer available",
    "post isn't available",  # seen live: post page of a missing post (in a browser)
    "the link to this photo or video may be broken",  # seen live: embed view of a missing post
)
_RATE_LIMIT_PHRASES = (
    "please wait a few minutes before you try again",
    "too many requests",
)
# Invisible direction marks (LRM, RLM, embeddings, overrides, isolates). Instagram puts an
# LRM after the date and at the end of the preview text.
_BIDI_MARKS = (
    "\N{LEFT-TO-RIGHT MARK}\N{RIGHT-TO-LEFT MARK}"
    "\N{LEFT-TO-RIGHT EMBEDDING}-\N{RIGHT-TO-LEFT OVERRIDE}"
    "\N{LEFT-TO-RIGHT ISOLATE}-\N{POP DIRECTIONAL ISOLATE}"
)
# en-US preview format: '12 likes, 3 comments - username on March 5, 2023: "caption".'
_META_CAPTION_RE = re.compile(
    rf"(?P<username>[A-Za-z0-9._]{{1,30}}) on (?P<date>[A-Z][a-z]+ \d{{1,2}}, \d{{4}})[{_BIDI_MARKS}]*: "
    rf"[\"“](?P<caption>.*)[\"”]\.?[\s{_BIDI_MARKS}]*$",
    re.DOTALL,
)
# Keys that real post objects carry. Other objects on the page (route parameters,
# analytics) can also have a "code" or "shortcode" equal to the shortcode.
_MEDIA_KEYS = {"pk", "id", "taken_at", "taken_at_timestamp", "media_type", "product_type"}
# A JSON string literal assigned to "contextJSON" (embed view).
_CONTEXT_JSON_RE = re.compile(r'"contextJSON":("(?:[^"\\]|\\.)*")')
# Page route in the post page's bootstrap data. Seen live: ...PolarisLoggedOutDesktopWWWPostRoute
# (a post) and ...PolarisErrorRoute (missing post). Reported by others: ...PolarisCAAIGLoginHomepageRoute.
_ROUTE_RE = re.compile(r'"canonicalRouteName"\s*:\s*"([^"]+)"')
_SOURCE_PRIORITY = {
    CaptionSource.MEDIA_JSON_EMBEDDED: 0,
    CaptionSource.MEDIA_JSON_NETWORK: 0,
    CaptionSource.EMBED_PAGE: 1,
    CaptionSource.META_DESCRIPTION: 2,
}


def analyze_capture(page: CapturedPage, shortcode: str) -> CaptionAnalysis:
    """Find the caption of `shortcode` in a captured page and decide the outcome."""
    soup = BeautifulSoup(page.html, "html.parser") if page.html else None
    signals = _page_signals(page, soup, shortcode)
    candidates: list[CaptionCandidate] = []

    # 1. The post's own data (complete caption), embedded in HTML or fetched by the page.
    media_sources: list[tuple[Any, CaptionSource]] = []
    if soup is not None:
        media_sources += [(data, CaptionSource.MEDIA_JSON_EMBEDDED) for data in _embedded_json(soup)]
    media_sources += [(item.body, CaptionSource.MEDIA_JSON_NETWORK) for item in page.network_json]
    for data, source in media_sources:
        for media in find_media(data, shortcode):
            signals.media_json_found = True
            # Logged-out post pages wrap the post: {"gating_ruling": ..., "if_not_gated_logged_out": {post}}.
            # A null inner post is assumed to mean Instagram withholds the post (not yet observed here).
            if "if_not_gated_logged_out" in media and media["if_not_gated_logged_out"] is None:
                signals.gated_for_logged_out = True
            has_caption_field, text = media_caption(media)
            if text and text.strip():
                candidates.append(
                    CaptionCandidate(
                        source=source,
                        text=text,
                        author=media_author(media),
                        coauthors=media_coauthors(media),
                        media=media_items(media),
                        truncated=False,
                    )
                )
            elif has_caption_field:
                signals.media_caption_empty = True
    if any(_is_rate_limit_response(item.body) for item in page.network_json):
        signals.rate_limit_message = True

    # 2. Rendered text: the embed view's caption block and the meta preview. Unlike the
    #    post data above, these carry no shortcode, so skip them when the page names another post.
    if soup is not None and not signals.other_post_shown:
        candidates += [c for c in (embed_caption(soup),) if c is not None]
        candidates += meta_captions(soup)

    candidates = _dedupe(candidates)
    best = choose_best(candidates)
    return CaptionAnalysis(outcome=_decide(page, signals, best), best=best, candidates=candidates, signals=signals)


def find_media(data: Any, shortcode: str) -> list[dict[str, Any]]:
    """Return every JSON object that describes the post with this shortcode.

    Instagram pages also carry data for *other* posts (suggestions, the author's
    recent posts), so matching on the shortcode is essential: otherwise we could
    import another post's caption. Objects without post fields (for example the
    page's route parameters, which include the shortcode and "caption": null)
    are ignored so they cannot be mistaken for a post without a caption.
    """
    return [
        node
        for node in _walk(data)
        if isinstance(node, dict)
        and (node.get("code") == shortcode or node.get("shortcode") == shortcode)
        and not _MEDIA_KEYS.isdisjoint(node)
    ]


def media_caption(media: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (has_caption_field, caption_text) for both known JSON shapes.

    has_caption_field distinguishes "this object says the caption is empty"
    from "this object is only a reference without caption data".
    """
    if "caption" in media:
        caption = media["caption"]
        if isinstance(caption, dict):
            text = caption.get("text")
            return True, text if isinstance(text, str) else None
        if isinstance(caption, str):
            return True, caption
        return True, None
    container = media.get("edge_media_to_caption")
    edges = container.get("edges") if isinstance(container, dict) else None
    if isinstance(edges, list):
        node = edges[0].get("node") if edges and isinstance(edges[0], dict) else None
        text = node.get("text") if isinstance(node, dict) else None
        return True, text if isinstance(text, str) else None
    return False, None


def _person(account: Any) -> PostPerson | None:
    """{"username": ..., "full_name": ...} as seen on post pages ("user") and in the embed view ("owner")."""
    if not isinstance(account, dict) or not isinstance(account.get("username"), str) or not account["username"]:
        return None
    full_name = account.get("full_name")
    return PostPerson(username=account["username"], full_name=full_name.strip() if isinstance(full_name, str) and full_name.strip() else None)


def media_author(media: dict[str, Any]) -> PostPerson | None:
    """The account that posted it, with its display name (seen live: "ריטה קדוש" for ritakadosh_)."""
    for key in ("user", "owner"):
        person = _person(media.get(key))
        if person is not None:
            return person
    return None


def media_coauthors(media: dict[str, Any]) -> list[PostPerson]:
    """Collaborators on a co-authored post (coauthor_producers), with their display names."""
    producers = media.get("coauthor_producers")
    if not isinstance(producers, list):
        return []
    return [person for person in map(_person, producers) if person is not None]


def media_items(media: dict[str, Any]) -> list[PostMediaItem]:
    """The post's pictures and videos, in order. Two shapes, both seen live (docs/instagram-feasibility.md):
    - post page: media_type 1 (image), 2 (video) or 8 (carousel, items in carousel_media); pictures in
      image_versions2.candidates (several sizes, sometimes without sizes: the first is the largest),
      videos in video_versions (no sizes; the first is the best);
    - embed view: display_url / display_resources, is_video and video_url, carousel items in
      edge_sidecar_to_children.edges[].node.
    """
    children = media.get("carousel_media")
    if not isinstance(children, list) or not children:
        sidecar = media.get("edge_sidecar_to_children")
        edges = sidecar.get("edges") if isinstance(sidecar, dict) else None
        children = [edge.get("node") for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []
    items = [child for child in children if isinstance(child, dict)] or [media]
    found = []
    for index, item in enumerate(items):
        image, width, height = _best_picture(item)
        videos = _video_urls(item)
        is_video = item.get("media_type") == 2 or item.get("is_video") is True or bool(videos)
        if image is None and not videos:
            continue  # nothing to show: not a media item after all
        found.append(
            PostMediaItem(
                index=index, kind="video" if is_video else "image", image_url=image, video_urls=videos,
                width=_int(item.get("original_width")) or width, height=_int(item.get("original_height")) or height,
            )
        )
    return found


def _best_picture(item: dict[str, Any]) -> tuple[str | None, int | None, int | None]:
    """The largest picture: by its size when given, else the first (Instagram lists the largest first)."""
    candidates = (item.get("image_versions2") or {}).get("candidates") if isinstance(item.get("image_versions2"), dict) else None
    pictures = [
        (c["url"], _int(c.get("width")), _int(c.get("height")))
        for c in candidates or []
        if isinstance(c, dict) and isinstance(c.get("url"), str)
    ]
    resources = item.get("display_resources")
    pictures += [
        (r["src"], _int(r.get("config_width")), _int(r.get("config_height")))
        for r in resources if isinstance(resources, list)
        for r in [r] if isinstance(r, dict) and isinstance(r.get("src"), str)
    ] if isinstance(resources, list) else []
    for key in ("display_url", "display_uri", "thumbnail_src"):
        if isinstance(item.get(key), str):
            pictures.append((item[key], None, None))
    if not pictures:
        return None, None, None
    sized = [p for p in pictures if p[1] and p[2]]
    return max(sized, key=lambda p: p[1] * p[2]) if sized else pictures[0]


def _video_urls(item: dict[str, Any]) -> list[str]:
    versions = item.get("video_versions")
    urls = [v["url"] for v in versions if isinstance(v, dict) and isinstance(v.get("url"), str)] if isinstance(versions, list) else []
    if isinstance(item.get("video_url"), str):
        urls.append(item["video_url"])
    return list(dict.fromkeys(urls))  # the same file listed twice is tried once


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def embed_caption(soup: BeautifulSoup) -> CaptionCandidate | None:
    """Caption block of the public embed view (/p/<code>/embed/captioned/)."""
    block = soup.select_one(".Caption")
    if block is None:
        return None
    block = copy.copy(block)  # detached copy, so the original soup is untouched
    username_tag = block.select_one(".CaptionUsername")
    username = username_tag.get_text(strip=True) if username_tag else None
    for tag in block.select(".CaptionUsername, .CaptionComments"):
        tag.decompose()
    text = _text_with_line_breaks(block).strip()
    if not text:
        return None
    return CaptionCandidate(
        source=CaptionSource.EMBED_PAGE, text=text, author=PostPerson(username=username) if username else None,
        truncated=_ends_with_ellipsis(text) or None,
    )


def meta_captions(soup: BeautifulSoup) -> list[CaptionCandidate]:
    """Caption preview in og:description / description meta tags."""
    found = []
    for attrs in ({"property": "og:description"}, {"name": "description"}):
        tag = soup.find("meta", attrs=attrs)
        content = tag.get("content") if isinstance(tag, Tag) else None
        if not isinstance(content, str):
            continue
        match = _META_CAPTION_RE.search(content)
        if match and match.group("caption").strip():
            caption = match.group("caption").strip()
            found.append(
                CaptionCandidate(
                    source=CaptionSource.META_DESCRIPTION,
                    text=caption,
                    author=PostPerson(username=match.group("username")),
                    truncated=True if _ends_with_ellipsis(caption) else None,
                )
            )
    return found


def choose_best(candidates: list[CaptionCandidate]) -> CaptionCandidate | None:
    """Prefer evidence of completeness, then the more reliable source, then the longer text."""
    if not candidates:
        return None
    completeness_rank = {False: 0, None: 1, True: 2}
    return min(
        candidates,
        key=lambda c: (completeness_rank[c.truncated], _SOURCE_PRIORITY[c.source], -len(c.text)),
    )


def _decide(page: CapturedPage, signals: PageSignals, best: CaptionCandidate | None) -> FetchOutcome:
    # A caption we found wins over page-level warnings: the visible page text
    # includes the caption itself, which may contain words like "try again".
    if best is not None:
        return FetchOutcome.CAPTION_FOUND if best.truncated is False else FetchOutcome.CAPTION_INCOMPLETE
    # What the page says comes before how the load ended: a login wall that
    # loaded slowly is still a login wall, not a reason to retry.
    if page.http_status == 429 or signals.rate_limit_message:
        return FetchOutcome.RATE_LIMITED
    if signals.media_caption_empty:
        return FetchOutcome.NO_CAPTION
    if signals.gated_for_logged_out or signals.login_redirect or signals.login_form or page.http_status in (401, 403):
        return FetchOutcome.LOGIN_REQUIRED
    if signals.unavailable_message or page.http_status == 404:
        return FetchOutcome.UNAVAILABLE
    if page.error_kind == "timeout":
        return FetchOutcome.TIMEOUT
    if page.error_kind is not None or (page.http_status or 0) >= 500:
        return FetchOutcome.ERROR
    return FetchOutcome.CAPTION_NOT_FOUND


def _page_signals(page: CapturedPage, soup: BeautifulSoup | None, shortcode: str) -> PageSignals:
    final_path = urlsplit(page.final_url or "").path.lower()
    requested_path = urlsplit(page.requested_url).path.lower()
    # Instagram may answer a logged-out visitor with a redirect to the login page,
    # a challenge page, or simply the homepage.
    login_redirect = page.final_url is not None and (
        final_path.startswith(("/accounts/login", "/challenge"))
        or (final_path in ("", "/") and requested_path not in ("", "/"))
    )
    text = _visible_text(soup).lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'") if soup is not None else ""
    route_match = _ROUTE_RE.search(page.html)
    route = route_match.group(1) if route_match else None
    post_addresses = _post_addresses(soup) if soup is not None else []
    return PageSignals(
        title=soup.title.get_text(strip=True) if soup is not None and soup.title else None,
        route=route,
        # The login page can also be served in place of the post, without a redirect (route name).
        login_redirect=login_redirect or (route is not None and "LoginHomepageRoute" in route),
        login_form=soup is not None and soup.select_one('input[name="password"]') is not None,
        # A missing post is served with HTTP 200: the error route (also in plain HTTP responses),
        # a visible message, or the embed view's EmbedBrokenMedia block.
        unavailable_message=any(phrase in text for phrase in _UNAVAILABLE_PHRASES)
        or (route is not None and route.endswith("PolarisErrorRoute"))
        or (soup is not None and soup.select_one(".EmbedBrokenMedia") is not None),
        rate_limit_message=any(phrase in text for phrase in _RATE_LIMIT_PHRASES),
        other_post_shown=bool(post_addresses) and not any(f"/{shortcode}/" in url for url in post_addresses),
    )


def _post_addresses(soup: BeautifulSoup) -> list[str]:
    """Addresses the page gives for the post it shows (seen live on both page types)."""
    found = []
    for tag, attribute in (
        (soup.find("meta", attrs={"property": "og:url"}), "content"),  # post page
        (soup.find("link", attrs={"rel": "canonical"}), "href"),  # post page
        (soup.select_one(".Embed[data-permalink]"), "data-permalink"),  # embed view
    ):
        value = tag.get(attribute) if isinstance(tag, Tag) else None
        if isinstance(value, str):
            found.append(value)
    return found


def _is_rate_limit_response(body: Any) -> bool:
    """GraphQL error code 1675004 or a "please wait a few minutes" message.

    These response shapes are documented by yt-dlp and instaloader (2026); they
    were not observed in our own probe runs.
    """
    for node in _walk(body):
        if isinstance(node, dict):
            message = node.get("message")
            if node.get("code") == 1675004 or (
                isinstance(message, str)
                and ("rate limit" in message.lower() or "please wait a few minutes" in message.lower())
            ):
                return True
    return False


def _embedded_json(soup: BeautifulSoup) -> Iterator[Any]:
    """JSON documents carried inside the page's <script> tags.

    The post page uses <script type="application/json">. The embed view instead
    keeps the post's data as a JSON *string* inside JavaScript
    ("contextJSON":"{...}"), so that string is decoded twice.
    """
    for script in soup.find_all("script"):
        text = script.string or ""
        if script.get("type") == "application/json":
            data = _decode_json(text)
            if data is not None:
                yield data
        elif "contextJSON" in text:
            for match in _CONTEXT_JSON_RE.finditer(text):
                try:
                    yield json.loads(json.loads(match.group(1)))
                except (ValueError, TypeError, RecursionError):
                    continue  # not a JSON string after all, or absurdly nested


def _decode_json(text: str) -> Any | None:
    """Decode a JSON document; also handles the `for (;;);` prefix and newline-delimited JSON."""
    text = text.strip()
    if text.startswith("for (;;);"):
        text = text[len("for (;;);") :]
    if not text:
        return None
    try:
        return json.loads(text)
    except RecursionError:
        return None  # absurdly nested: not something Instagram's real pages contain
    except ValueError:
        pass
    parts = []
    for line in text.splitlines():
        try:
            parts.append(json.loads(line))
        except (ValueError, RecursionError):
            return None
    return parts or None


def _walk(node: Any) -> Iterator[Any]:
    """Yield every value in a decoded JSON document (iterative: page JSON can be deeply nested)."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, dict):
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))


def _text_with_line_breaks(tag: Tag) -> str:
    tag = copy.copy(tag)
    for line_break in tag.find_all("br"):
        line_break.replace_with("\n")
    return tag.get_text("")


def _visible_text(soup: BeautifulSoup) -> str:
    hidden = {"script", "style", "noscript", "template"}
    return " ".join(
        str(text)
        for text in soup.find_all(string=True)
        # Comments, doctype and CDATA are never shown to the visitor.
        if not isinstance(text, PreformattedString) and text.parent is not None and text.parent.name not in hidden
    )


def _ends_with_ellipsis(text: str) -> bool:
    return text.rstrip().endswith(("...", "…"))


def _dedupe(candidates: list[CaptionCandidate]) -> list[CaptionCandidate]:
    """Drop repeated candidates, keeping the first one found.

    On real post pages the requested post also appears again inside its author's
    timeline, as a copy without the co-author list; the main object comes first.
    """
    seen: set[tuple[CaptionSource, str]] = set()
    unique = []
    for candidate in candidates:
        key = (candidate.source, " ".join(candidate.text.split()))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


# ---------------------------------------------------------------------------
# Capture: load a page and keep the raw material
# ---------------------------------------------------------------------------

_MAX_JSON_BYTES = 5_000_000
# Instagram pages observed: 0.2-1 MB. Checked after decompression, so the limit is approximate.
_MAX_PAGE_BYTES = 10_000_000


async def capture_with_http(
    url: str, *, timeout_s: float = 20.0, transport: httpx2.AsyncBaseTransport | None = None
) -> CapturedPage:
    """Plain HTTP GET (no JavaScript). Uses HTTPX2's own User-Agent, not a disguised one.

    timeout_s bounds each network step; the whole request gets twice that.
    `transport` lets tests replace the network (httpx2.MockTransport).
    """
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout_s * 2):
            async with httpx2.AsyncClient(
                follow_redirects=True,
                max_redirects=5,
                timeout=timeout_s,
                headers={"Accept-Language": "en-US,en;q=0.9"},
                transport=transport,
            ) as client:
                async with client.stream("GET", url) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > _MAX_PAGE_BYTES:
                            raise _TooLarge()
                    html = body.decode(response.encoding or "utf-8", errors="replace")
    except (httpx2.TimeoutException, TimeoutError) as exc:
        return CapturedPage(
            method="http", requested_url=url, error_kind="timeout", error=str(exc) or "Timed out",
            elapsed_ms=_elapsed_ms(started),
        )
    except httpx2.HTTPError as exc:
        return CapturedPage(
            method="http", requested_url=url, error_kind="network", error=f"{type(exc).__name__}: {exc}",
            elapsed_ms=_elapsed_ms(started),
        )
    except _TooLarge:
        return CapturedPage(
            method="http", requested_url=url, error_kind="network",
            error=f"Response larger than {_MAX_PAGE_BYTES // 1_000_000} MB", elapsed_ms=_elapsed_ms(started),
        )
    return CapturedPage(
        method="http",
        requested_url=url,
        final_url=str(response.url),
        http_status=response.status_code,
        html=html,
        user_agent=response.request.headers.get("user-agent"),
        elapsed_ms=_elapsed_ms(started),
    )


class _TooLarge(Exception):
    """The response exceeded _MAX_PAGE_BYTES."""


async def capture_with_browser(
    url: str,
    *,
    headless: bool = True,
    channel: str | None = None,
    timeout_s: float = 30.0,
    screenshot_path: str | None = None,
) -> CapturedPage:
    """Load the page in a fresh, logged-out Chromium profile and keep what it received.

    `channel` may name an installed browser ("msedge", "chrome"); by default
    Playwright's bundled Chromium is used. No cookies or login are reused.
    The whole capture is bounded by twice timeout_s.
    """
    started = time.monotonic()
    result: dict[str, Any] = {"method": "browser", "requested_url": url}
    try:
        # One overall deadline: some Playwright calls (page.content, page.evaluate)
        # have no timeout of their own. Leaving the block also shuts the browser down.
        async with asyncio.timeout(timeout_s * 2):
            await _capture_in_browser(url, result, headless, channel, timeout_s, screenshot_path)
    except TimeoutError:
        result.setdefault("error_kind", "timeout")
        result.setdefault("error", f"Capture did not finish within {timeout_s * 2:g} s")
    return CapturedPage(**result, elapsed_ms=_elapsed_ms(started))


async def _capture_in_browser(
    url: str, result: dict[str, Any], headless: bool, channel: str | None, timeout_s: float, screenshot_path: str | None
) -> None:
    """Fill `result` step by step, so whatever was read survives a later failure."""
    json_responses: list[Response] = []

    def remember_json_response(response: Response) -> None:
        if response.request.resource_type in ("xhr", "fetch") and _is_instagram_data_url(response.url):
            json_responses.append(response)

    async with async_playwright() as playwright:
        try:
            # Bound the launch too: Playwright's default launch timeout is 180 s.
            browser = await playwright.chromium.launch(headless=headless, channel=channel, timeout=timeout_s * 1000)
        except PlaywrightError as exc:
            error = _first_line(exc)
            if "Executable doesn't exist" in str(exc):
                error += " (run: uv run playwright install chromium)"
            result.update(error_kind="browser", error=error)
            return
        result["browser_version"] = browser.version
        try:
            context = await browser.new_context(locale="en-US", viewport={"width": 1280, "height": 900})
            page = await context.new_page()
        except PlaywrightError as exc:
            result.update(error_kind="browser", error=_first_line(exc))
            return
        page.on("response", remember_json_response)
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
            result["http_status"] = response.status if response else None
            await _let_page_settle(page, timeout_s)
        except PlaywrightTimeoutError as exc:
            result.update(error_kind="timeout", error=_first_line(exc))
        except PlaywrightError as exc:
            message = _first_line(exc)
            result.update(error_kind="network" if "net::ERR" in message else "browser", error=message)

        # Keep whatever loaded, even after a timeout: it may show a login wall or
        # partial content. The HTML matters most, so read it first; the rest is best-effort.
        result["final_url"] = page.url
        result["html"] = await _read_html(page)
        if not result["html"] and "error_kind" not in result:
            result.update(error_kind="browser", error="Could not read the page content")
        with contextlib.suppress(PlaywrightError):
            result["user_agent"] = await page.evaluate("() => navigator.userAgent")
        result["network_json"] = await _read_json_bodies(json_responses)
        if screenshot_path:
            with contextlib.suppress(PlaywrightError, OSError):
                await page.screenshot(path=screenshot_path, timeout=10_000)
        with contextlib.suppress(PlaywrightError):
            await browser.close()


async def _let_page_settle(page: Page, timeout_s: float) -> None:
    # Instagram keeps some connections open, so these waits are capped; we continue with what has loaded.
    for state, share in (("load", 0.5), ("networkidle", 0.2)):
        with contextlib.suppress(PlaywrightTimeoutError):
            await page.wait_for_load_state(state, timeout=timeout_s * share * 1000)


async def _read_html(page: Page) -> str:
    """page.content() fails while the page is navigating (e.g. a JavaScript redirect): wait, then retry once."""
    for attempt in range(2):
        try:
            return await page.content()
        except PlaywrightError:
            if attempt == 0:
                with contextlib.suppress(PlaywrightError):
                    await page.wait_for_load_state("domcontentloaded", timeout=5_000)
    return ""


async def _read_json_bodies(responses: list[Response]) -> list[NetworkJson]:
    bodies = []
    for response in responses:
        try:
            raw = await response.body()
        except PlaywrightError:
            continue  # body no longer available (e.g. redirect responses)
        if len(raw) > _MAX_JSON_BYTES:
            continue
        data = _decode_json(raw.decode("utf-8", errors="replace"))
        if data is not None:
            bodies.append(NetworkJson(url=response.url, status=response.status, body=data))
    return bodies


def _is_instagram_data_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    is_instagram = host == "instagram.com" or host.endswith(".instagram.com")
    return is_instagram and parts.path.startswith(("/graphql", "/api/"))


def _first_line(exc: Exception) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0]


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


# ---------------------------------------------------------------------------
# Retrieval: what an import uses
# ---------------------------------------------------------------------------

PageName = Literal["post_page", "embed_view"]


class RetrievalAttempt(BaseModel):
    """One page load and what it showed: kept for the log and to explain a failure."""

    page: PageName
    outcome: FetchOutcome
    http_status: int | None = None
    elapsed_ms: int = 0
    error: str | None = None


class CaptionRetrieval(BaseModel):
    """What reading one post for an import gave."""

    url: str  # the post's canonical address
    outcome: FetchOutcome
    caption: str | None = None  # exactly as Instagram has it, invisible direction marks included
    complete: bool = False  # True only for a caption taken from the post's own data
    retrieved_from: PageName | None = None
    author: PostPerson | None = None
    coauthors: list[PostPerson] = Field(default_factory=list)
    media: list[PostMediaItem] = Field(default_factory=list)  # the post's pictures and videos, in order
    attempts: list[RetrievalAttempt] = Field(default_factory=list)


# Instagram's own answers about the post (or about us): another page would not change them.
_FINAL_OUTCOMES = {FetchOutcome.RATE_LIMITED, FetchOutcome.UNAVAILABLE, FetchOutcome.NO_CAPTION}
# When no page had the caption, the more telling reason is reported.
_FAILURE_ORDER = [
    FetchOutcome.RATE_LIMITED,
    FetchOutcome.LOGIN_REQUIRED,
    FetchOutcome.UNAVAILABLE,
    FetchOutcome.NO_CAPTION,
    FetchOutcome.CAPTION_NOT_FOUND,
    FetchOutcome.TIMEOUT,
    FetchOutcome.ERROR,
]


async def retrieve_caption(
    ref: InstagramRef, *, browser_timeout_s: float = 20.0, http_timeout_s: float = 10.0
) -> CaptionRetrieval:
    """Read one post's caption as milestone 1 recommended (docs/instagram-feasibility.md):

    1. the post page in a fresh, logged-out browser, reading the post's own data (complete);
    2. only if that gave no complete caption, and Instagram did not say that the post is unavailable
       or has no caption, or that we should slow down: the public embed view, once, over plain HTTP;
    3. if neither gave the complete caption, a preview from either page, marked incomplete;
    4. otherwise the reason.
    At most two page loads, each bounded (twice its timeout). Never a login, a retry loop or a
    disguised client.
    """
    analyses: list[tuple[PageName, CaptionAnalysis]] = []
    attempts: list[RetrievalAttempt] = []
    for page_name, capture in (
        ("post_page", lambda: capture_with_browser(ref.canonical_url, timeout_s=browser_timeout_s)),
        ("embed_view", lambda: capture_with_http(ref.embed_url, timeout_s=http_timeout_s)),
    ):
        page = await capture()
        analysis = analyze_capture(page, ref.shortcode)
        analyses.append((page_name, analysis))
        attempts.append(
            RetrievalAttempt(
                page=page_name, outcome=analysis.outcome, http_status=page.http_status, elapsed_ms=page.elapsed_ms,
                error=page.error,
            )
        )
        if analysis.outcome is FetchOutcome.CAPTION_FOUND or analysis.outcome in _FINAL_OUTCOMES:
            break
    return _combine(ref, analyses, attempts)


def _combine(
    ref: InstagramRef, analyses: list[tuple[PageName, CaptionAnalysis]], attempts: list[RetrievalAttempt]
) -> CaptionRetrieval:
    """The complete caption if a page had it; else a preview (the post page's first); else the reason."""
    for wanted in (FetchOutcome.CAPTION_FOUND, FetchOutcome.CAPTION_INCOMPLETE):
        for page_name, analysis in analyses:
            if analysis.outcome is wanted and analysis.best is not None:
                return CaptionRetrieval(
                    url=ref.canonical_url,
                    outcome=wanted,
                    caption=analysis.best.text,
                    complete=wanted is FetchOutcome.CAPTION_FOUND,
                    retrieved_from=page_name,
                    author=analysis.best.author,
                    coauthors=analysis.best.coauthors,
                    media=analysis.best.media or _media_from_any(analyses),
                    attempts=attempts,
                )
    outcome = min((analysis.outcome for _, analysis in analyses), key=_FAILURE_ORDER.index)
    return CaptionRetrieval(url=ref.canonical_url, outcome=outcome, attempts=attempts)


def _media_from_any(analyses: list[tuple[PageName, CaptionAnalysis]]) -> list[PostMediaItem]:
    """When the caption came from a preview, the media may still have come with a page's post data."""
    for _, analysis in analyses:
        for candidate in analysis.candidates:
            if candidate.media:
                return candidate.media
    return []


def retrieve_caption_blocking(ref: InstagramRef) -> CaptionRetrieval:
    """retrieve_caption from synchronous code (an API endpoint runs in a worker thread), in an event loop
    of its own. On Windows that must be a Proactor loop: Playwright starts the browser as a child
    process, which the Selector loop that `uvicorn --reload` uses cannot do (milestone 1 finding)."""
    loop_factory = asyncio.ProactorEventLoop if sys.platform == "win32" else None
    return asyncio.run(retrieve_caption(ref), loop_factory=loop_factory)
