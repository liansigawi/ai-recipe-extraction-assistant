"""Pictures and videos of recipes: saved once on this computer, and shown from here.

Files are content-addressed: <data folder>/media/<two hex digits>/<sha256>.<ext>. The same bytes (a post
imported twice, the same picture uploaded twice) are one file, shared by every attachment that uses it.
media_files has a row per file; recipe_media has a row per attachment (a recipe's picture or video).
A file is deleted only when no attachment uses it any more (collect_garbage), so removing an attachment
or a recipe never breaks another recipe's media.

Downloads (a post's media, right after its page was read: Instagram's addresses expire) are bounded:
only from Instagram's media servers, a size limit per picture, per video and per post, a time limit
per request and for the whole post, at most MAX_ITEMS items. Every file's type is checked from its
first bytes, whatever the server says. A failure is reported item by item and never fails an import.
"""

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import load_settings
from app.db import utc_now
from app.errors import ApiError
from app.importers.instagram import InstagramRef, PostMediaItem

log = logging.getLogger("uvicorn.error")

MAX_IMAGE_BYTES = 20_000_000
MAX_VIDEO_BYTES = 150_000_000  # a reel of a minute or two; longer videos stay a poster with a link
MAX_POST_BYTES = 400_000_000
MAX_UPLOAD_BYTES = MAX_IMAGE_BYTES
MAX_ITEMS = 20  # Instagram's own limit for a carousel
POST_DEADLINE_S = 180.0  # all of a post's media
REQUEST_TIMEOUT = httpx2.Timeout(30.0, connect=10.0)
MEDIA_HOSTS = (".cdninstagram.com", ".fbcdn.net")  # where Instagram's post data points (seen live)
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "video/mp4": ".mp4"}
IMAGES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
VIDEOS = {"video/mp4"}


class MediaError(Exception):
    """Why one file could not be saved, in Hebrew, for the report."""


def media_root(data_dir: Path) -> Path:
    return data_dir / "media"


def get_media_root() -> Path:
    """FastAPI dependency: the media folder, under the data folder (read fresh, like the database's)."""
    return media_root(load_settings().data_dir)


def get_media_transport() -> httpx2.BaseTransport | None:
    """FastAPI dependency: how media files are downloaded. None: the network. Tests give a stand-in."""
    return None


def report_issue(report: "MediaReport") -> schemas.Issue | None:
    """A review point when not every item of the post was saved here (nothing when all were)."""
    if report.found == 0:
        return schemas.Issue(kind="media_incomplete", message="בנתוני הפוסט לא נמצאו תמונות או סרטונים לשמירה.")
    if not report.failed and not report.thumbnails_only:
        return None
    parts = [f"מהפוסט נשמרו כאן במלואם {report.saved} מתוך {report.found} התמונות והסרטונים."]
    if report.thumbnails_only:
        parts.append(
            "סרטון אחד נשמר רק כתמונה מתוכו, עם קישור לצפייה בפוסט."
            if report.thumbnails_only == 1
            else f"{report.thumbnails_only} סרטונים נשמרו רק כתמונה מתוכם, עם קישור לצפייה בפוסט."
        )
    if report.failed:
        parts.append("פריט אחד לא נשמר." if report.failed == 1 else f"{report.failed} פריטים לא נשמרו.")
    parts.append('אפשר לנסות שוב בכפתור "שליפת מדיה מהפוסט" בתצוגת המתכון.')
    return schemas.Issue(kind="media_incomplete", message=" ".join(parts))


def sniff(head: bytes) -> str | None:
    """The file's type from its first bytes (the server's Content-Type is not trusted)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[4:8] == b"ftyp":
        return "video/mp4"
    return None


@dataclass
class StoredFile:
    """A file written under the media folder: its hash, path (relative to the folder), type and size."""

    sha256: str
    path: str
    content_type: str
    size_bytes: int


def _place(root: Path, digest: str, content_type: str, temporary: Path) -> StoredFile:
    """Move a finished temporary file to its content address (or drop it if that file is already there)."""
    relative = f"{digest[:2]}/{digest}{EXTENSIONS[content_type]}"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        temporary.unlink(missing_ok=True)
    else:
        os.replace(temporary, target)
    return StoredFile(digest, relative, content_type, target.stat().st_size)


def store_bytes(root: Path, data: bytes, allowed: set[str]) -> StoredFile:
    """Bytes in hand (an upload): checked, then written once at their content address."""
    content_type = sniff(data[:16])
    if content_type not in allowed:
        raise MediaError("הקובץ אינו תמונה מסוג שאפשר לשמור (JPEG, PNG, WebP או GIF).")
    temporary = root / "tmp" / f"{uuid.uuid4().hex}.part"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_bytes(data)
    return _place(root, hashlib.sha256(data).hexdigest(), content_type, temporary)


def download(client: httpx2.Client, url: str, root: Path, max_bytes: int, allowed: set[str], deadline: float) -> StoredFile:
    """One file from Instagram's media servers, streamed to disk while it is hashed, within the limits."""
    host = (urlsplit(url).hostname or "").lower()
    if not host.endswith(MEDIA_HOSTS):
        raise MediaError("הכתובת אינה משרתי המדיה של אינסטגרם.")
    if time.monotonic() > deadline:
        raise MediaError("נגמר הזמן שהוקצב להורדת המדיה של הפוסט.")
    temporary = root / "tmp" / f"{uuid.uuid4().hex}.part"
    temporary.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    head = b""
    size = 0
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise MediaError(f"השרת ענה {response.status_code}.")
            declared = int(response.headers.get("content-length") or 0)
            if declared > max_bytes:
                raise MediaError(f"הקובץ גדול מדי ({declared / 1e6:.0f} MB; עד {max_bytes / 1e6:.0f} MB).")
            with temporary.open("wb") as out:
                for chunk in response.iter_bytes():
                    if not head:
                        head = chunk[:16]
                    size += len(chunk)
                    if size > max_bytes:
                        raise MediaError(f"הקובץ גדול מדי (יותר מ-{max_bytes / 1e6:.0f} MB).")
                    if time.monotonic() > deadline:
                        raise MediaError("נגמר הזמן שהוקצב להורדת המדיה של הפוסט.")
                    digest.update(chunk)
                    out.write(chunk)
        content_type = sniff(head)
        if content_type not in allowed:
            raise MediaError("הקובץ שהתקבל אינו תמונה או סרטון.")
        return _place(root, digest.hexdigest(), content_type, temporary)
    except httpx2.TimeoutException:
        raise MediaError("השרת לא ענה בזמן.") from None
    except httpx2.HTTPError as error:
        raise MediaError(f"שגיאת רשת ({type(error).__name__}).") from None
    finally:
        temporary.unlink(missing_ok=True)


def _file_row(session: Session, stored: StoredFile) -> models.MediaFile:
    row = session.scalar(select(models.MediaFile).where(models.MediaFile.sha256 == stored.sha256))
    if row is None:
        row = models.MediaFile(
            sha256=stored.sha256, path=stored.path, content_type=stored.content_type, size_bytes=stored.size_bytes,
            created_at=utc_now(),
        )
        session.add(row)
        session.flush()  # INSERT now: the attachment needs the id
    else:
        row.path = stored.path  # the same bytes: the same address (rewritten if the file had gone)
    return row


@dataclass
class MediaReport:
    """What happened to a post's media: every item counted once."""

    found: int = 0  # items in the post
    saved: int = 0  # pictures and videos saved here
    thumbnails_only: int = 0  # videos that could not be saved: their poster is, with a link to the post
    failed: int = 0  # nothing of the item could be saved
    already_had: int = 0  # the recipe had it already (a repeated fetch)
    problems: list[str] = field(default_factory=list)

    def schema(self) -> schemas.MediaReport:
        return schemas.MediaReport(**self.__dict__)


@dataclass
class _Fetched:
    item: PostMediaItem
    picture: StoredFile | None = None
    video: StoredFile | None = None


def attach_post_media(
    session: Session, root: Path, recipe: models.Recipe, ref: InstagramRef, items: list[PostMediaItem],
    transport: httpx2.BaseTransport | None = None,
) -> MediaReport:
    """Download a post's pictures and videos and attach them to the recipe, in the post's order.

    An item the recipe already has (the same post and place) is left alone, so fetching again adds
    nothing twice; a video that was saved only as its poster is tried again. The recipe's content,
    credit and cover choice are not touched. The downloads happen before the database is written, so
    the database is not held while they run."""
    session.refresh(recipe, attribute_names=["media"])  # what the database has now, not an earlier load
    report = MediaReport(found=len(items))
    have = {
        media.post_index: media
        for media in recipe.media
        if media.post_shortcode == ref.shortcode and media.post_index is not None
    }
    deadline = time.monotonic() + POST_DEADLINE_S
    total = 0
    fetched: list[_Fetched] = []
    if len(items) > MAX_ITEMS:
        report.problems.append(f"לפוסט יש {len(items)} פריטים; נשמרו לכל היותר הראשונים {MAX_ITEMS}.")
        report.failed += len(items) - MAX_ITEMS
    with httpx2.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True, transport=transport) as client:
        for item in items[:MAX_ITEMS]:
            existing = have.get(item.index)
            if existing is not None and (existing.kind == "image" or existing.file_id is not None):
                report.already_had += 1
                continue
            got = _Fetched(item)
            number = f"פריט {item.index + 1}"
            if item.image_url is not None and (existing is None or existing.thumbnail_file_id is None):
                try:
                    got.picture = download(client, item.image_url, root, MAX_IMAGE_BYTES, IMAGES, deadline)
                    total += got.picture.size_bytes
                except MediaError as error:
                    report.problems.append(f"{number} ({'תמונה' if item.kind == 'image' else 'תמונת הסרטון'}): {error}")
            if item.kind == "video":
                reasons = []
                for url in item.video_urls[:3]:  # the best first; a smaller one if it is too large
                    if total > MAX_POST_BYTES:
                        reasons.append("הפוסט כולו גדול מהמגבלה.")
                        break
                    try:
                        got.video = download(client, url, root, MAX_VIDEO_BYTES, VIDEOS, deadline)
                        total += got.video.size_bytes
                        break
                    except MediaError as error:
                        reasons.append(str(error))
                if got.video is None:
                    report.problems.append(f"{number} (סרטון): {reasons[-1] if reasons else 'לא נמצא קובץ הסרטון.'}")
            fetched.append(got)

    for got in fetched:
        item, existing = got.item, have.get(got.item.index)
        picture = _file_row(session, got.picture) if got.picture else None
        video = _file_row(session, got.video) if got.video else None
        if item.kind == "image":
            if picture is None:
                report.failed += 1
                continue
            report.saved += 1
            session.add(_attachment(recipe, ref, item, file=picture, thumbnail=None))
            continue
        if existing is not None:  # a video saved earlier as its poster only
            if video is not None:
                existing.file_id, existing.status = video.id, "saved"
                report.saved += 1
            else:
                report.thumbnails_only += 1
            continue
        if video is None and picture is None:
            report.failed += 1
            continue
        if video is None:
            report.thumbnails_only += 1
        else:
            report.saved += 1
        session.add(_attachment(recipe, ref, item, file=video, thumbnail=picture))
    session.commit()
    log.info(
        "Media of %s: %d items, %d saved, %d posters only, %d failed, %d already here",
        ref.canonical_url, report.found, report.saved, report.thumbnails_only, report.failed, report.already_had,
    )
    return report


def _attachment(
    recipe: models.Recipe, ref: InstagramRef, item: PostMediaItem, file: models.MediaFile | None,
    thumbnail: models.MediaFile | None,
) -> models.RecipeMedia:
    return models.RecipeMedia(
        recipe_id=recipe.id, kind=item.kind, status="saved" if file is not None else "thumbnail_only",
        file_id=file.id if file else None, thumbnail_file_id=thumbnail.id if thumbnail else None, origin="instagram",
        post_url=ref.canonical_url, post_shortcode=ref.shortcode, post_index=item.index, width=item.width,
        height=item.height, created_at=utc_now(),
    )


def attach_upload(session: Session, root: Path, recipe: models.Recipe, data: bytes) -> models.RecipeMedia:
    """A picture the person uploaded: checked by its first bytes, saved once, added after the others."""
    try:
        stored = store_bytes(root, data, IMAGES)
    except MediaError as error:
        raise ApiError(415, "unsupported_media", str(error)) from None
    file = _file_row(session, stored)
    attachment = models.RecipeMedia(
        recipe_id=recipe.id, kind="image", status="saved", file_id=file.id, origin="upload", created_at=utc_now()
    )
    session.add(attachment)
    session.commit()
    return attachment


def attach_website_image(session: Session, root: Path, recipe: models.Recipe, page_url: str, data: bytes) -> models.RecipeMedia:
    """A recipe page's main picture, read from the site (app/importers/website.py): checked by its first
    bytes and saved once, like any picture. MediaError when it is not a picture that can be saved."""
    stored = store_bytes(root, data, IMAGES)
    file = _file_row(session, stored)
    attachment = models.RecipeMedia(
        recipe_id=recipe.id, kind="image", status="saved", file_id=file.id, origin="website", post_url=page_url,
        created_at=utc_now(),
    )
    session.add(attachment)
    session.commit()
    return attachment


def set_cover(session: Session, recipe: models.Recipe, media_id: int | None) -> None:
    """The recipe's cover: one of its pictures or video posters, or None for the default (the first)."""
    session.refresh(recipe, attribute_names=["media"])
    chosen = None
    if media_id is not None:
        chosen = next((media for media in recipe.media if media.id == media_id), None)
        if chosen is None:
            raise ApiError(404, "media_not_found", f"Recipe {recipe.id} has no attachment {media_id}.")
        if chosen.kind == "video" and chosen.thumbnail_file_id is None:
            raise ApiError(422, "cover_needs_a_picture", "This video has no picture to show as a cover.")
    for media in recipe.media:
        media.is_cover = False
    session.flush()  # the one-cover index: clear before setting
    if chosen is not None:
        chosen.is_cover = True
    session.commit()


def remove(session: Session, root: Path, recipe: models.Recipe, media_id: int) -> None:
    session.refresh(recipe, attribute_names=["media"])
    attachment = next((media for media in recipe.media if media.id == media_id), None)
    if attachment is None:
        raise ApiError(404, "media_not_found", f"Recipe {recipe.id} has no attachment {media_id}.")
    recipe.media.remove(attachment)  # delete-orphan: DELETE FROM recipe_media WHERE id = ?
    session.commit()
    collect_garbage(session, root)


def collect_garbage(session: Session, root: Path) -> int:
    """Delete the files no attachment uses any more (after an attachment or a recipe was removed).
    A file another recipe still uses stays. Returns how many were deleted."""
    used = select(models.RecipeMedia.file_id).where(models.RecipeMedia.file_id.is_not(None)).union(
        select(models.RecipeMedia.thumbnail_file_id).where(models.RecipeMedia.thumbnail_file_id.is_not(None))
    )
    unused = list(session.scalars(select(models.MediaFile).where(models.MediaFile.id.not_in(used))))
    paths = [root / row.path for row in unused]
    for row in unused:
        session.delete(row)
    session.commit()
    for path in paths:  # after the commit: a failed commit never leaves a row without its file
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            log.warning("Could not delete the unused media file %s: %s", path, error)
    return len(unused)


def file_path(root: Path, row: models.MediaFile) -> Path:
    """The file on disk, refusing anything outside the media folder."""
    path = (root / row.path).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ApiError(404, "media_not_found", "No such file.")
    return path
