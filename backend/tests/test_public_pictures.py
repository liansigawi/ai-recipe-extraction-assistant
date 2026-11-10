"""Public copies of uploaded pictures (scripts/public_pictures.py): nothing but the pixels, upright, in sRGB,
not larger than the limit, and the original file untouched."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import ExifTags, Image, ImageCms

from scripts import public_pictures
from scripts.public_pictures import PictureError, location_in, metadata_in, sanitized_copy

BLUE, RED = (20, 40, 220), (220, 30, 30)
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
XMP_WITH_GPS = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
    b'<rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude="32,4.5N" exif:GPSLongitude="34,46.8E"/>'
    b"</rdf:RDF></x:xmpmeta>"
)


def phone_photo(width: int = 40, height: int = 20, orientation: int = 6, fmt: str = "JPEG") -> bytes:
    """A photo as a phone saves it: the left half blue, the right half red, stored sideways with an EXIF
    orientation that turns it upright, the place it was taken (GPS), the phone's make, XMP with the place
    again, a comment and a colour profile."""
    picture = Image.new("RGB", (width, height), RED)
    picture.paste(BLUE, (0, 0, width // 2, height))
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    exif[ExifTags.Base.Make] = "PhoneMaker"
    exif[ExifTags.Base.DateTime] = "2026:11:09 18:30:00"
    exif[ExifTags.IFD.GPSInfo] = {1: "N", 2: (32.0, 4.0, 30.0), 3: "E", 4: (34.0, 46.0, 48.0)}
    out = BytesIO()
    if fmt == "JPEG":
        picture.save(out, "JPEG", quality=95, exif=exif, icc_profile=SRGB, comment=b"our kitchen", xmp=XMP_WITH_GPS)
    else:
        picture.save(out, fmt, exif=exif, icc_profile=SRGB)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    picture = Image.open(BytesIO(data))
    picture.load()
    return picture


def mostly(pixel: tuple[int, ...], color: tuple[int, int, int]) -> bool:
    return all(abs(a - b) <= 30 for a, b in zip(pixel[:3], color))


def test_a_phone_photo_is_published_without_its_metadata_upright_and_the_original_untouched(tmp_path: Path):
    photo = phone_photo()
    source = tmp_path / "upload.jpg"
    source.write_bytes(photo)
    assert location_in(photo) and set(metadata_in(photo)) >= {"a location (GPS)", "EXIF", "icc_profile", "xmp", "comment"}

    clean = sanitized_copy(source)

    assert source.read_bytes() == photo  # only read
    assert (clean.extension, clean.content_type) == ("jpg", "image/jpeg")
    assert metadata_in(clean.data) == [] and not location_in(clean.data)
    assert b"PhoneMaker" not in clean.data and b"our kitchen" not in clean.data and b"GPS" not in clean.data
    picture = opened(clean.data)
    # Stored 40 x 20 and turned a quarter clockwise by its orientation: upright it is 20 x 40, the blue half on top.
    assert (clean.width, clean.height) == picture.size == (20, 40)
    assert mostly(picture.getpixel((10, 5)), BLUE) and mostly(picture.getpixel((10, 35)), RED)


def test_a_large_photo_is_made_smaller_keeping_its_shape(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(public_pictures, "MAX_SIDE", 30)
    source = tmp_path / "big.jpg"
    source.write_bytes(phone_photo(width=120, height=60, orientation=1))
    clean = sanitized_copy(source)
    assert (clean.width, clean.height) == (30, 15)


def test_a_png_keeps_its_transparency_and_a_gif_becomes_its_first_frame_as_a_png(tmp_path: Path):
    transparent = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    transparent.paste((255, 200, 0, 255), (0, 0, 5, 10))
    out = BytesIO()
    transparent.save(out, "PNG", pnginfo=None, icc_profile=SRGB)
    (tmp_path / "a.png").write_bytes(out.getvalue())
    clean = sanitized_copy(tmp_path / "a.png")
    picture = opened(clean.data)
    assert clean.extension == "png" and picture.mode == "RGBA" and picture.getpixel((8, 5))[3] == 0 and metadata_in(clean.data) == []

    frames = [Image.new("P", (8, 8), 1), Image.new("P", (8, 8), 2)]
    gif = BytesIO()
    frames[0].save(gif, "GIF", save_all=True, append_images=frames[1:], comment=b"made here")
    (tmp_path / "b.gif").write_bytes(gif.getvalue())
    clean = sanitized_copy(tmp_path / "b.gif")
    assert (clean.extension, clean.content_type) == ("png", "image/png") and metadata_in(clean.data) == []


def test_a_webp_stays_a_webp_without_metadata(tmp_path: Path):
    (tmp_path / "c.webp").write_bytes(phone_photo(fmt="WEBP", orientation=1))
    clean = sanitized_copy(tmp_path / "c.webp")
    assert clean.extension == "webp" and metadata_in(clean.data) == [] and opened(clean.data).size == (40, 20)


def test_what_is_not_a_picture_is_refused(tmp_path: Path):
    (tmp_path / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x04" * 100)
    with pytest.raises(PictureError, match="cannot be read as a picture"):
        sanitized_copy(tmp_path / "x.png")
    assert metadata_in(b"not a picture") == ["nothing readable as a picture"] and not location_in(b"not a picture")


def test_a_location_written_only_in_xmp_is_found():
    picture = Image.new("RGB", (4, 4), BLUE)
    out = BytesIO()
    picture.save(out, "JPEG", xmp=XMP_WITH_GPS)
    assert location_in(out.getvalue()) and "xmp" in metadata_in(out.getvalue())
