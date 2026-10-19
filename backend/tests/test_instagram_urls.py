"""Which pasted links are accepted, and how they are normalized."""

import pytest

from app.importers.instagram import InvalidInstagramUrl, parse_instagram_url


@pytest.mark.parametrize(
    ("url", "shortcode", "kind"),
    [
        ("https://www.instagram.com/p/Cm1mCdCpSzJ/", "Cm1mCdCpSzJ", "p"),
        ("https://instagram.com/p/Cm1mCdCpSzJ", "Cm1mCdCpSzJ", "p"),
        ("instagram.com/p/DPbKEn-CnUt/?igsh=MWQ1ZGUxMzBkMA==", "DPbKEn-CnUt", "p"),
        ("instagram.com/p/DPbKEn-CnUt/?next=https://example.com/", "DPbKEn-CnUt", "p"),  # "://" only in the query
        ("https://www.instagram.com/reel/DANUmOOIcRM/?utm_source=ig_web_copy_link", "DANUmOOIcRM", "reel"),
        ("http://www.instagram.com/reel/DANUmOOIcRM/", "DANUmOOIcRM", "reel"),
        ("https://www.instagram.com/reels/DANUmOOIcRM/", "DANUmOOIcRM", "reel"),
        ("https://www.instagram.com/tv/DANUmOOIcRM/", "DANUmOOIcRM", "p"),
        ("https://m.instagram.com/p/Cm1mCdCpSzJ/#comments", "Cm1mCdCpSzJ", "p"),
        ("https://instagr.am/p/Cm1mCdCpSzJ/", "Cm1mCdCpSzJ", "p"),
        ("https://www.instagram.com/some.creator/p/Cm1mCdCpSzJ/?img_index=1", "Cm1mCdCpSzJ", "p"),
        ("https://www.instagram.com/p/Cm1mCdCpSzJ/embed/captioned/", "Cm1mCdCpSzJ", "p"),
        ("  https://www.instagram.com/p/Cm1mCdCpSzJ/  ", "Cm1mCdCpSzJ", "p"),
    ],
)
def test_parse_supported_urls(url, shortcode, kind):
    ref = parse_instagram_url(url)
    assert (ref.shortcode, ref.kind) == (shortcode, kind)
    assert ref.canonical_url == f"https://www.instagram.com/{kind}/{shortcode}/"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/p/Cm1mCdCpSzJ/",
        "https://notinstagram.com/p/Cm1mCdCpSzJ/",
        "https://instagram.com.evil.example/p/Cm1mCdCpSzJ/",
        "https://instagram.com@evil.example/p/Cm1mCdCpSzJ/",
        "https://[www.instagram.com/p/Cm1mCdCpSzJ/",  # malformed host: must not escape as a plain ValueError
        "ftp://www.instagram.com/p/Cm1mCdCpSzJ/",
        "https://www.instagram.com/some.creator/",
        "https://www.instagram.com/stories/p/3141592653589793/",  # a story by a user named "p", not a post
        "https://www.instagram.com/reels/audio/3141592653589793/",
        "https://www.instagram.com/p/",
        "https://www.instagram.com/p/ab/",
    ],
)
def test_reject_unsupported_urls(url):
    with pytest.raises(InvalidInstagramUrl):
        parse_instagram_url(url)


def test_share_links_get_a_specific_message():
    with pytest.raises(InvalidInstagramUrl, match="Share links"):
        parse_instagram_url("https://www.instagram.com/share/p/BAXkQ4zhdq/")
