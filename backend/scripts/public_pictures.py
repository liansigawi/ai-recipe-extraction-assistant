"""Public copies of uploaded pictures, without what the file says about where and how it was taken.

A photo uploaded from a phone can carry the place it was taken (EXIF GPS), the device and the time, and other
embedded data (XMP, IPTC, comments, a colour profile). Its public copy is made from the picture's pixels alone:
turned upright by its EXIF orientation, its colours converted to sRGB when it carries a colour profile, at most
MAX_SIDE pixels on its long side, and encoded again with no metadata at all; then read back to confirm that.
The original file is only read, never changed.

Also the site's own check (scripts/publish_public.py): no published picture may carry a location.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import ExifTags, Image, ImageCms, ImageOps, UnidentifiedImageError

MAX_SIDE = 2048  # the public copy's long side at most: sharp on any screen; a phone photo is often 4000 px or more
JPEG_QUALITY = 92  # visually the same as the original, at a fraction of a phone photo's size
WEBP_QUALITY = 90
# The public copy's format, by the upload's (Pillow's name -> the format written, its extension, its type).
# A GIF's first frame becomes a PNG: a cover is one picture.
OUTPUT = {
    "JPEG": ("JPEG", "jpg", "image/jpeg"),
    "PNG": ("PNG", "png", "image/png"),
    "WEBP": ("WEBP", "webp", "image/webp"),
    "GIF": ("PNG", "png", "image/png"),
}
# What Pillow reports when it opens a file and that says nothing about where or how the picture was taken:
# the JPEG header's density, how a file is encoded, and the animation settings every WebP file states.
ENCODING_INFO = {
    "jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi", "progressive", "progression", "adobe", "adobe_transform",
    "loop", "background", "duration", "timestamp",
}


class PictureError(Exception):
    """The picture cannot be published: unreadable, of a kind not handled, or still carrying metadata."""


@dataclass(frozen=True)
class CleanPicture:
    data: bytes
    extension: str  # "jpg", "png" or "webp"
    content_type: str
    width: int
    height: int


def sanitized_copy(source: Path) -> CleanPicture:
    """The public copy of the picture at `source` (see the module's description)."""
    try:
        with Image.open(source) as original:
            if original.format not in OUTPUT:
                raise PictureError(f"a {original.format} picture is not published")
            written_as, extension, content_type = OUTPUT[original.format]
            original.seek(0)  # a GIF: its first frame
            picture = ImageOps.exif_transpose(original)  # a copy in memory, upright; the file stays as it is
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise PictureError(f"it cannot be read as a picture ({error})") from None
    picture = _in_srgb(picture)
    picture = _plain_mode(picture, written_as)
    if max(picture.size) > MAX_SIDE:
        picture.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    # A new image from the pixels alone: nothing of the file they came from travels with them.
    clean = Image.frombytes(picture.mode, picture.size, picture.tobytes())
    out = BytesIO()
    options = {"JPEG": {"quality": JPEG_QUALITY, "optimize": True}, "PNG": {"optimize": True}, "WEBP": {"quality": WEBP_QUALITY}}
    clean.save(out, written_as, **options[written_as])
    data = out.getvalue()
    left = metadata_in(data)
    if left:
        raise PictureError(f"its copy still carries {', '.join(left)}")
    return CleanPicture(data, extension, content_type, clean.width, clean.height)


def metadata_in(data: bytes) -> list[str]:
    """What a picture file carries besides its pixels and how they are encoded: a location, EXIF, XMP, a colour
    profile, comments, text. Empty for a clean copy; a file that is not a picture says so."""
    try:
        with Image.open(BytesIO(data)) as picture:
            found = ["a location (GPS)"] if _gps(picture) else []
            if len(picture.getexif()):
                found.append("EXIF")
            found += sorted(key for key in picture.info if key not in ENCODING_INFO)  # xmp, icc_profile, comment, exif, PNG text…
            return found
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return ["nothing readable as a picture"]


def location_in(data: bytes) -> bool:
    """Whether a picture file says where it was taken: EXIF GPS, or GPS fields in its XMP. A file that is not
    a readable picture holds no location that a viewer could read."""
    try:
        with Image.open(BytesIO(data)) as picture:
            return _gps(picture)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return False


def _gps(picture: Image.Image) -> bool:
    if picture.getexif().get_ifd(ExifTags.IFD.GPSInfo):
        return True
    xmp = picture.info.get("xmp") or picture.info.get("XML:com.adobe.xmp") or b""
    return b"GPSLatitude" in (xmp if isinstance(xmp, bytes) else xmp.encode("utf-8", "replace"))


def _in_srgb(picture: Image.Image) -> Image.Image:
    """The colours as the profile meant them, in sRGB, so that leaving the profile out changes nothing a
    browser shows. An unusable profile leaves the pixels as they are."""
    profile = picture.info.get("icc_profile")
    if not profile:
        return picture
    mode = "RGBA" if picture.mode in ("RGBA", "LA", "PA") else "RGB"
    try:
        if picture.mode not in ("RGB", "RGBA", "CMYK"):
            picture = picture.convert(mode)
        return ImageCms.profileToProfile(picture, ImageCms.ImageCmsProfile(BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode=mode)
    except (ImageCms.PyCMSError, OSError, ValueError):
        return picture


def _plain_mode(picture: Image.Image, written_as: str) -> Image.Image:
    """Pixels the output format holds directly; a palette's transparency kept as an alpha channel."""
    if written_as == "JPEG":
        return picture if picture.mode in ("RGB", "L") else picture.convert("RGB")
    if picture.mode in ("RGB", "RGBA", "L", "LA"):
        return picture
    transparent = picture.mode == "PA" or "transparency" in picture.info
    return picture.convert("RGBA" if transparent else "RGB")
