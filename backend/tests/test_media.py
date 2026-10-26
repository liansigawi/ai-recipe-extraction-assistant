"""Media: the post's list of pictures and videos, bounded downloads, files stored once, attachments.

The post shapes mirror the live captures of 2026-10-26 (a reel, a mixed carousel of video, image and
video, a 14-photo carousel); downloads go to a stand-in transport, never to Instagram.
"""

import time

import httpx2
import pytest
from sqlalchemy import select

from app import media, models
from app.db import utc_now
from app.importers.instagram import PostMediaItem, media_items, parse_instagram_url

CDN = "https://instagram.ftlv1-1.fna.fbcdn.net"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x01" * 2000
OTHER_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x02" * 2000
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x03" * 5000
PNG = b"\x89PNG\r\n\x1a\n" + b"\x04" * 100
REF = parse_instagram_url("https://www.instagram.com/p/CLJ5G9rDi1a/")


def picture(url, width=None, height=None):
    candidate = {"url": url}
    if width:
        candidate |= {"width": width, "height": height}
    return candidate


# --- The post's media list ---------------------------------------------------------------------------


def test_a_reel_is_one_video_with_its_poster():
    reel = {"media_type": 2, "original_width": 720, "original_height": 1280,
            "image_versions2": {"candidates": [picture(f"{CDN}/big.jpg", 1080, 1920), picture(f"{CDN}/small.jpg", 480, 852)]},
            "video_versions": [{"type": 101, "url": f"{CDN}/v.mp4"}, {"type": 102, "url": f"{CDN}/v.mp4"}, {"type": 103, "url": f"{CDN}/v2.mp4"}]}
    [item] = media_items(reel)
    assert (item.index, item.kind, item.image_url, item.width, item.height) == (0, "video", f"{CDN}/big.jpg", 720, 1280)
    assert item.video_urls == [f"{CDN}/v.mp4", f"{CDN}/v2.mp4"]  # the same file listed twice is tried once


def test_a_mixed_carousel_keeps_its_order_and_kinds():
    carousel = {"media_type": 8, "image_versions2": {"candidates": [picture(f"{CDN}/cover.jpg")]}, "carousel_media": [
        {"media_type": 2, "image_versions2": {"candidates": [picture(f"{CDN}/p0.jpg", 720, 900)]}, "video_versions": [{"url": f"{CDN}/v0.mp4"}]},
        {"media_type": 1, "original_width": 1440, "original_height": 1800, "image_versions2": {"candidates": [picture(f"{CDN}/i1.jpg"), picture(f"{CDN}/i1s.jpg")]}},
        {"media_type": 2, "image_versions2": {"candidates": [picture(f"{CDN}/p2.jpg", 720, 900)]}, "video_versions": [{"url": f"{CDN}/v2.mp4"}]},
    ]}
    items = media_items(carousel)
    assert [(i.index, i.kind) for i in items] == [(0, "video"), (1, "image"), (2, "video")]
    # Without sizes the first candidate is the picture (Instagram lists the largest first).
    assert items[1].image_url == f"{CDN}/i1.jpg" and (items[1].width, items[1].height) == (1440, 1800)


def test_a_single_image_post():
    [item] = media_items({"media_type": 1, "image_versions2": {"candidates": [picture(f"{CDN}/a.jpg", 640, 640), picture(f"{CDN}/b.jpg", 1080, 1080)]}})
    assert (item.kind, item.image_url) == ("image", f"{CDN}/b.jpg")  # the largest by its size


def test_the_embed_views_shape_too():
    sidecar = {"__typename": "GraphSidecar", "display_url": f"{CDN}/cover.jpg", "edge_sidecar_to_children": {"edges": [
        {"node": {"is_video": False, "display_resources": [{"src": f"{CDN}/s.jpg", "config_width": 640, "config_height": 800},
                                                           {"src": f"{CDN}/l.jpg", "config_width": 1080, "config_height": 1350}]}},
        {"node": {"is_video": True, "display_url": f"{CDN}/poster.jpg", "video_url": f"{CDN}/clip.mp4"}},
    ]}}
    items = media_items(sidecar)
    assert [(i.kind, i.image_url, i.video_urls) for i in items] == [
        ("image", f"{CDN}/l.jpg", []), ("video", f"{CDN}/poster.jpg", [f"{CDN}/clip.mp4"])
    ]


# --- Downloads ---------------------------------------------------------------------------------------


def serve(files: dict[str, bytes | int | Exception], headers: dict[str, dict] | None = None):
    """A stand-in for the network: each address answers bytes, a status code, or raises."""
    asked: list[str] = []

    def handler(request):
        url = str(request.url)
        asked.append(url)
        answer = files.get(url, 404)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, int):
            return httpx2.Response(answer)
        return httpx2.Response(200, content=answer, headers=(headers or {}).get(url, {}))

    return httpx2.MockTransport(handler), asked


def fetch(url, files, *, limit=10_000_000, allowed=media.IMAGES, root, headers=None):
    transport, _ = serve(files, headers)
    with httpx2.Client(transport=transport) as client:
        return media.download(client, url, root, limit, allowed, time.monotonic() + 60)


def test_a_picture_is_stored_at_its_content_address(tmp_path):
    stored = fetch(f"{CDN}/a.jpg", {f"{CDN}/a.jpg": JPEG}, root=tmp_path)
    assert stored.content_type == "image/jpeg" and stored.size_bytes == len(JPEG)
    assert stored.path == f"{stored.sha256[:2]}/{stored.sha256}.jpg"
    assert (tmp_path / stored.path).read_bytes() == JPEG
    assert list((tmp_path / "tmp").iterdir()) == []  # nothing left half-written


@pytest.mark.parametrize(
    ("url", "files", "message"),
    [
        ("https://example.com/a.jpg", {}, "משרתי המדיה"),  # only Instagram's media servers
        (f"{CDN}/a.jpg", {f"{CDN}/a.jpg": 403}, "403"),
        (f"{CDN}/a.jpg", {f"{CDN}/a.jpg": b"<html>login</html>"}, "אינו תמונה"),  # the type is checked from the bytes
        (f"{CDN}/a.jpg", {f"{CDN}/a.jpg": JPEG * 10}, "גדול מדי"),  # over the limit while streaming
        (f"{CDN}/a.jpg", {f"{CDN}/a.jpg": httpx2.ReadTimeout("slow")}, "בזמן"),
        (f"{CDN}/a.jpg", {f"{CDN}/a.jpg": httpx2.ConnectError("no network")}, "רשת"),
    ],
)
def test_downloads_are_bounded_and_checked(tmp_path, url, files, message):
    with pytest.raises(media.MediaError, match=message):
        fetch(url, files, limit=len(JPEG) * 5, root=tmp_path)
    assert not any(tmp_path.rglob("*.jpg"))


def test_a_declared_size_over_the_limit_is_refused_before_reading(tmp_path):
    with pytest.raises(media.MediaError, match="גדול מדי"):
        fetch(f"{CDN}/a.jpg", {f"{CDN}/a.jpg": JPEG}, limit=100, root=tmp_path, headers={f"{CDN}/a.jpg": {"content-length": "999999"}})


# --- Attaching a post's media ------------------------------------------------------------------------

ITEMS = [
    PostMediaItem(index=0, kind="video", image_url=f"{CDN}/p0.jpg", video_urls=[f"{CDN}/v0.mp4"], width=720, height=900),
    PostMediaItem(index=1, kind="image", image_url=f"{CDN}/i1.jpg", width=1440, height=1800),
    PostMediaItem(index=2, kind="video", image_url=f"{CDN}/p2.jpg", video_urls=[f"{CDN}/v2.mp4"]),
]
EVERYTHING = {f"{CDN}/p0.jpg": JPEG, f"{CDN}/v0.mp4": MP4, f"{CDN}/i1.jpg": OTHER_JPEG, f"{CDN}/p2.jpg": JPEG, f"{CDN}/v2.mp4": MP4}


@pytest.fixture
def recipe(client):
    """A recipe in the test database, and a session on it."""
    session = client.app.state.session_factory()
    row = models.Recipe(title="עוגיות", ingredient_groups=[], step_groups=[], notes=[], created_at=utc_now(), updated_at=utc_now())
    session.add(row)
    session.commit()
    yield session, row
    session.close()


def attachments(session, row):
    session.expire_all()
    return sorted(session.get(models.Recipe, row.id).media, key=lambda m: m.post_index if m.post_index is not None else 99)


def test_every_item_is_saved_in_the_posts_order_and_the_same_bytes_once(recipe, tmp_path):
    session, row = recipe
    transport, _ = serve(EVERYTHING)
    report = media.attach_post_media(session, tmp_path, row, REF, ITEMS, transport)
    assert (report.found, report.saved, report.thumbnails_only, report.failed) == (3, 3, 0, 0)
    saved = attachments(session, row)
    assert [(m.post_index, m.kind, m.status, m.file.content_type) for m in saved] == [
        (0, "video", "saved", "video/mp4"), (1, "image", "saved", "image/jpeg"), (2, "video", "saved", "video/mp4")
    ]
    assert saved[0].thumbnail.content_type == "image/jpeg" and saved[0].post_url == REF.canonical_url
    # The two posters and the two videos are the same bytes: one file each.
    assert len(list(session.scalars(select(models.MediaFile)))) == 3


def test_a_video_that_cannot_be_saved_keeps_its_poster_and_the_report_says_so(recipe, tmp_path):
    session, row = recipe
    transport, _ = serve(EVERYTHING | {f"{CDN}/v2.mp4": 403, f"{CDN}/i1.jpg": 404})
    report = media.attach_post_media(session, tmp_path, row, REF, ITEMS, transport)
    assert (report.saved, report.thumbnails_only, report.failed) == (1, 1, 1)
    assert len(report.problems) == 2 and "פריט 3 (סרטון)" in report.problems[1]
    saved = attachments(session, row)
    assert [(m.post_index, m.status) for m in saved] == [(0, "saved"), (2, "thumbnail_only")]
    assert saved[1].file is None and saved[1].thumbnail is not None
    issue = media.report_issue(report)
    assert issue.kind == "media_incomplete" and "1 מתוך 3" in issue.message and "רק כתמונה" in issue.message


def test_fetching_again_adds_nothing_twice_and_completes_a_video_saved_as_its_poster(recipe, tmp_path):
    session, row = recipe
    transport, _ = serve(EVERYTHING | {f"{CDN}/v2.mp4": 403})
    media.attach_post_media(session, tmp_path, row, REF, ITEMS, transport)
    transport, asked = serve(EVERYTHING)
    report = media.attach_post_media(session, tmp_path, row, REF, ITEMS, transport)
    assert (report.already_had, report.saved) == (2, 1)
    assert asked == [f"{CDN}/v2.mp4"]  # only the missing video: its poster is here already
    assert [(m.post_index, m.status) for m in attachments(session, row)] == [(0, "saved"), (1, "saved"), (2, "saved")]


def test_more_items_than_the_limit_are_reported(recipe, tmp_path, monkeypatch):
    session, row = recipe
    monkeypatch.setattr(media, "MAX_ITEMS", 2)
    transport, _ = serve(EVERYTHING)
    report = media.attach_post_media(session, tmp_path, row, REF, ITEMS, transport)
    assert (report.saved, report.failed) == (2, 1) and "3 פריטים" in report.problems[0]


def test_an_unused_file_is_deleted_and_a_shared_one_kept(recipe, tmp_path):
    session, row = recipe
    other = models.Recipe(title="עותק", ingredient_groups=[], step_groups=[], notes=[], created_at=utc_now(), updated_at=utc_now())
    session.add(other)
    session.commit()
    transport, _ = serve(EVERYTHING)
    media.attach_post_media(session, tmp_path, row, REF, ITEMS[1:2], transport)
    media.attach_post_media(session, tmp_path, other, REF, ITEMS[1:2], transport)  # a copy of the post: the same file
    [shared] = session.scalars(select(models.MediaFile))
    path = tmp_path / shared.path
    first = attachments(session, row)[0]
    media.remove(session, tmp_path, session.get(models.Recipe, row.id), first.id)
    assert path.exists()  # the copy still uses it
    session.delete(session.get(models.Recipe, other.id))
    session.commit()
    assert media.collect_garbage(session, tmp_path) == 1
    assert not path.exists() and list(session.scalars(select(models.MediaFile))) == []
