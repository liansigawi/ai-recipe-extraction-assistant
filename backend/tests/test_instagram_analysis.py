"""Offline tests for finding the caption in a captured page and deciding the outcome.

Captions are invented. The page structures mirror the saved live captures
(data/instagram-probe/...), trimmed to the parts the analyzer reads.
"""

import json

import pytest

from app.importers.instagram import (
    CaptionCandidate,
    CaptionSource,
    CapturedPage,
    FetchOutcome,
    _decode_json,
    analyze_capture,
    choose_best,
    find_media,
    media_caption,
)

CODE = "Cm1mCdCpSzJ"
URL = f"https://www.instagram.com/p/{CODE}/"
EMBED_URL = f"https://www.instagram.com/p/{CODE}/embed/captioned/"
LRM = "\N{LEFT-TO-RIGHT MARK}"
RLM = "\N{RIGHT-TO-LEFT MARK}"
ESCAPED_SLASH = "\\/"  # how the embed view writes "/" inside its JSON
CAPTION = "פשטידת תרד קלה\nמצרכים:\n2 כוסות תרד\n3 ביצים\n\nאופים 30–35 דקות ב-180 מעלות."
OTHER_CAPTION = "פוסט אחר של אותה יוצרת, עם כיתוב ארוך הרבה יותר, כדי שבחירה לפי אורך תיכשל."


def page(html: str = "", *, method: str = "browser", requested_url: str = URL, final_url: str | None = None,
         http_status: int | None = 200, **extra) -> CapturedPage:
    return CapturedPage(method=method, requested_url=requested_url, final_url=final_url or requested_url,
                        http_status=http_status, html=html, **extra)


# --- Page shapes seen live (trimmed) ----------------------------------------------------------


def serverjs(*require_entries) -> dict:
    """The bootstrap wrapper that carries data on real post pages."""
    return {"require": [["ScheduledServerJS", "handle", None, [{"__bbox": {"require": list(require_entries)}}]]]}


def post_page(*docs: dict, body: str = "") -> str:
    scripts = "".join(f'<script type="application/json" data-sjs="">{json.dumps(doc)}</script>' for doc in docs)
    return f"<html><head><title>Instagram</title></head><body>{body}{scripts}</body></html>"


def route_params_doc() -> dict:
    # Real path .../initialRouteInfo/route/params: keyed "shortcode", "caption": null, no post fields.
    params = {"shortcode": CODE, "caption": None, "permalink_key": "p", "igsh": None, "utm_source": None}
    return serverjs(["PolarisRouter", "init", [], [{"initialRouteInfo": {"route": {"params": params}}}]])


def post_data_doc(caption: str | None = CAPTION, coauthors: tuple[str, ...] = ()) -> dict:
    """xig_polaris_media -> if_not_gated_logged_out -> post, as on real logged-out post pages.

    As seen live, the author's timeline is nested inside the post, includes other
    posts with their captions, and repeats the requested post without its co-authors.
    """
    post = {"code": CODE, "pk": "1001", "id": "1001_1", "media_type": 2, "product_type": "clips"}
    caption_field = {"pk": "2001", "text": caption} if caption is not None else None
    timeline = {"edges": [
        {"node": {"code": "OtherPost01", "pk": "1002", "id": "1002_1", "caption": {"text": OTHER_CAPTION},
                  "user": {"username": "baker"}}},
        {"node": {**post, "caption": caption_field, "user": {"username": "baker"}}},
    ]}
    inner = {**post, "caption": caption_field,
             "coauthor_producers": [{"pk": "7", "username": name} for name in coauthors],
             "user": {"pk": "1", "username": "baker", "polaris_ordered_timeline_connection": timeline}}
    wrapper = {"pk": "1001", "code": CODE, "id": "1001_1", "gating_ruling": None, "if_not_gated_logged_out": inner}
    preloader = ["adp_PolarisLoggedOutDesktopWWWPostRootContentQueryRelayPreloader_1",
                 {"__bbox": {"result": {"data": {"xig_polaris_media": wrapper}}}}]
    return serverjs(["RelayPrefetchedStreamCache", "next", [], preloader])


EMBED_BLOCK = (
    '<div class="Caption">'
    '<a class="CaptionUsername" href="https://www.instagram.com/baker/?utm_source=ig_embed" target="_blank">baker</a>'
    "<br /><br />"
    "עוגת גבינה פירורים 🍰 <br />"
    f"{LRM}מצרכים לבצק: <br />"
    "200 גרם קמח<br />"
    "100 גרם חמאה קרה<br /><br />"
    'צילום: <a href="/friend.photos/?utm_source=ig_embed">&#064;friend.photos</a> <br /><br />'
    '<a href="/explore/tags/cake/?utm_source=ig_embed" dir="rtl" class="_5wj-">#עוגה</a> '
    '<a href="/explore/tags/cheesecake/?utm_source=ig_embed">#cheesecake</a>'
    f'<div class="CaptionComments"><a class="CaptionCommentsExpand" href="{URL}">View all 12 comments</a></div>'
    "</div>"
)
EMBED_TEXT = f"עוגת גבינה פירורים 🍰 \n{LRM}מצרכים לבצק: \n200 גרם קמח\n100 גרם חמאה קרה\n\nצילום: @friend.photos \n\n#עוגה #cheesecake"


def embed_view(block: str = EMBED_BLOCK, *, data_text: str | None = EMBED_TEXT, permalink_code: str = CODE) -> str:
    """The embed view: a rendered caption block, plus the post data as a JSON string inside a script."""
    script = ""
    if data_text is not None:
        inner = {"context": {"type": "GraphVideo", "shortcode": CODE},
                 "gql_data": {"shortcode_media": {"__typename": "GraphVideo", "id": "1001", "shortcode": CODE,
                                                  "product_type": "clips", "owner": {"username": "baker"},
                                                  "edge_media_to_caption": {"edges": [{"node": {"text": data_text}}]}}}}
        literal = json.dumps(json.dumps(inner).replace("/", ESCAPED_SLASH))
        script = '<script>s.handle({"require":[["PolarisEmbedSimple","init",[],[{"contextJSON":' + literal + "}]]]});</script>"
    embed = f'<div class="Embed" data-permalink="https://www.instagram.com/reel/{permalink_code}/?utm_source=ig_embed">{block}</div>'
    return f"<html><head><title>Instagram</title></head><body>{embed}{script}</body></html>"


def meta_page(caption: str, *, og_url: str | None = None) -> str:
    """og:description as on real post pages: an LRM after the date and at the end (both seen live)."""
    content = f"12 likes, 3 comments - some.baker on June 12, 2024{LRM}: &quot;{caption}&quot;. {LRM}"
    url_tag = f'<meta property="og:url" content="{og_url}">' if og_url else ""
    return f'<html><head><meta property="og:description" content="{content}">{url_tag}</head><body></body></html>'


def candidate(source: CaptionSource, text: str, truncated: bool | None) -> CaptionCandidate:
    return CaptionCandidate(source=source, text=text, truncated=truncated)


# --- Finding the requested post -----------------------------------------------------------------


def test_post_page_picks_requested_post_from_real_nesting():
    analysis = analyze_capture(page(post_page(route_params_doc(), post_data_doc(coauthors=("partner.shop",)))), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND
    assert analysis.best.text == CAPTION  # not the longer caption of the other post in the timeline
    assert analysis.best.author.username == "baker"
    # from the main object, not the timeline copy
    assert [person.username for person in analysis.best.coauthors] == ["partner.shop"]
    assert [c.source for c in analysis.candidates] == [CaptionSource.MEDIA_JSON_EMBEDDED]  # copy deduplicated
    assert analysis.signals.media_caption_empty is False  # the route parameters were ignored


def test_route_parameters_alone_are_not_a_post_without_caption():
    # The saved plain-HTTP post pages look like this: route parameters, no post data.
    analysis = analyze_capture(page(post_page(route_params_doc()), method="http"), CODE)
    assert analysis.signals.media_json_found is False
    assert analysis.outcome is FetchOutcome.CAPTION_NOT_FOUND  # "could not read", never "no caption"


def test_find_media_matches_only_the_requested_shortcode():
    found = find_media(post_data_doc(), CODE)
    assert found and all(node["code"] == CODE for node in found)


def test_media_caption_supports_both_known_shapes_and_survives_odd_ones():
    assert media_caption({"caption": {"text": "a"}}) == (True, "a")
    assert media_caption({"edge_media_to_caption": {"edges": [{"node": {"text": "b"}}]}}) == (True, "b")
    assert media_caption({"caption": None}) == (True, None)
    assert media_caption({"edge_media_to_caption": {"edges": []}}) == (True, None)
    assert media_caption({"code": CODE}) == (False, None)
    assert media_caption({"edge_media_to_caption": ["unexpected"]}) == (False, None)
    assert media_caption({"edge_media_to_caption": {"edges": [{"node": "unexpected"}]}}) == (True, None)


def test_caption_from_a_network_response():
    body = {"data": {"xdt_shortcode_media": {"id": "1", "shortcode": CODE,
                                             "edge_media_to_caption": {"edges": [{"node": {"text": CAPTION}}]}}}}
    captured = page("<html><body></body></html>",
                    network_json=[{"url": "https://www.instagram.com/graphql/query", "status": 200, "body": body}])
    analysis = analyze_capture(captured, CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND
    assert analysis.best.source is CaptionSource.MEDIA_JSON_NETWORK


def test_preview_of_a_different_post_is_not_used():
    # Rendered text carries no shortcode, so the page's own address must name the requested post.
    other = "https://www.instagram.com/some.baker/reel/OtherPost01/"
    analysis = analyze_capture(page(meta_page("עוגה של פוסט אחר", og_url=other)), CODE)
    assert analysis.signals.other_post_shown is True
    assert analysis.candidates == []
    assert analysis.outcome is FetchOutcome.CAPTION_NOT_FOUND


def test_embed_block_of_a_different_post_is_not_used():
    analysis = analyze_capture(page(embed_view(data_text=None, permalink_code="OtherPost01"), method="http"), CODE)
    assert analysis.candidates == []


def test_preview_naming_the_requested_post_is_used():
    analysis = analyze_capture(page(meta_page("עוגה", og_url=f"https://www.instagram.com/some.baker/reel/{CODE}/")), CODE)
    assert analysis.best.text == "עוגה"


# --- Completeness and choosing the best candidate ---------------------------------------------


def test_choose_best_prefers_complete_caption_over_longer_unverified_text():
    complete = candidate(CaptionSource.MEDIA_JSON_EMBEDDED, "קמח, סוכר", False)
    embed = candidate(CaptionSource.EMBED_PAGE, "קמח, סוכר, ועוד טקסט שנוסף בתצוגה", None)
    preview = candidate(CaptionSource.META_DESCRIPTION, "קמח, סוכר, ועוד טקסט ארוך עוד יותר...", True)
    assert choose_best([preview, embed, complete]) is complete


def test_choose_best_prefers_unverified_text_over_visibly_cut_text():
    unknown = candidate(CaptionSource.META_DESCRIPTION, "שורה אחת", None)
    cut = candidate(CaptionSource.EMBED_PAGE, "שורה אחת ועוד הרבה...", True)
    assert choose_best([cut, unknown]) is unknown


def test_choose_best_prefers_embed_block_over_meta_preview():
    meta = candidate(CaptionSource.META_DESCRIPTION, "טקסט ארוך יותר מהבלוק", None)
    embed = candidate(CaptionSource.EMBED_PAGE, "טקסט", None)
    assert choose_best([meta, embed]) is embed


def test_choose_best_prefers_longer_text_within_a_tier():
    short = candidate(CaptionSource.MEDIA_JSON_EMBEDDED, "קצר", False)
    longer = candidate(CaptionSource.MEDIA_JSON_NETWORK, "ארוך יותר", False)
    assert choose_best([short, longer]) is longer


def test_embed_view_data_and_rendered_block_agree():
    analysis = analyze_capture(page(embed_view(), method="http", requested_url=EMBED_URL), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND
    assert analysis.best.source is CaptionSource.MEDIA_JSON_EMBEDDED
    assert analysis.best.text == EMBED_TEXT
    block = next(c for c in analysis.candidates if c.source is CaptionSource.EMBED_PAGE)
    assert (block.text, block.author.username) == (EMBED_TEXT, "baker")  # seen live: identical to the data


def test_embed_block_alone_is_unverified_and_keeps_mentions_and_hashtags():
    analysis = analyze_capture(page(embed_view(data_text=None), method="http", requested_url=EMBED_URL), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_INCOMPLETE
    assert analysis.best.source is CaptionSource.EMBED_PAGE
    assert analysis.best.truncated is None
    assert analysis.best.text == EMBED_TEXT


def test_embed_block_ending_with_ellipsis_is_marked_cut():
    block = '<div class="Caption"><a class="CaptionUsername">baker</a><br /><br />עוגה עם הרבה שכבות…</div>'
    analysis = analyze_capture(page(embed_view(block, data_text=None), method="http"), CODE)
    assert analysis.best.truncated is True


def test_meta_preview_in_raw_http_source_format():
    # Raw HTTP source: Hebrew as hex entities, both meta tags with the same content (seen live).
    caption = "עוגה בחושה\nמצרכים: 3 ביצים"
    encoded = "".join(f"&#x{ord(char):x};" if ord(char) > 127 else char for char in caption)
    content = f"12K likes, 345 comments - some.baker_ on June 12, 2024{LRM}: &quot;{encoded}&quot;. {LRM}"
    html = (f'<html><head><meta property="og:description" content="{content}" />'
            f'<meta name="description" content="{content}" /></head><body></body></html>')
    analysis = analyze_capture(page(html, method="http"), CODE)
    assert [c.source for c in analysis.candidates] == [CaptionSource.META_DESCRIPTION]
    assert (analysis.best.text, analysis.best.author.username) == (caption, "some.baker_")
    assert analysis.best.truncated is None
    assert analysis.outcome is FetchOutcome.CAPTION_INCOMPLETE  # a preview is never trusted as complete


@pytest.mark.parametrize("ending", ["…", "..."])
def test_meta_preview_cut_with_an_ellipsis_is_marked_cut(ending):
    analysis = analyze_capture(page(meta_page(f"עוגה עם הרבה שכבות{ending}")), CODE)
    assert analysis.best.truncated is True
    assert analysis.outcome is FetchOutcome.CAPTION_INCOMPLETE


def test_caption_is_kept_verbatim_including_direction_marks_and_trailing_spaces():
    # Seen live: RLM/LRM inside a caption and spaces before line breaks. The stored original keeps them.
    caption = f"{RLM}עוגה בחושה \n{LRM}3 ביצים L\n\nאופים 40 דק׳ "
    analysis = analyze_capture(page(post_page(post_data_doc(caption))), CODE)
    assert analysis.best.text == caption


# --- Outcomes -------------------------------------------------------------------------------------


def test_caption_wins_over_a_login_modal():
    modal = '<div role="dialog"><input name="username"><input name="password" type="password"></div>'
    analysis = analyze_capture(page(post_page(post_data_doc(), body=modal)), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND
    assert analysis.signals.login_form is True


def test_caption_mentioning_rate_limit_words_is_still_found():
    # The visible page includes the caption itself; its words must not be mistaken for a block page.
    caption = "Too many requests for this recipe! Please wait a few minutes before you try again to slice."
    analysis = analyze_capture(page(post_page(post_data_doc(caption), body=f"<span>{caption}</span>")), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND


def test_caption_survives_a_timeout_after_the_page_loaded():
    captured = page(post_page(post_data_doc()), error_kind="timeout", error="Timeout 30000ms exceeded")
    assert analyze_capture(captured, CODE).outcome is FetchOutcome.CAPTION_FOUND


def test_post_without_caption():
    analysis = analyze_capture(page(post_page(post_data_doc(caption=None))), CODE)
    assert analysis.outcome is FetchOutcome.NO_CAPTION
    assert analysis.outcome.post_was_read


def test_post_without_caption_beats_a_login_modal():
    modal = '<div role="dialog"><input name="password" type="password"></div>'
    analysis = analyze_capture(page(post_page(post_data_doc(caption=None), body=modal)), CODE)
    assert analysis.outcome is FetchOutcome.NO_CAPTION


LOGIN_URL = "https://www.instagram.com/accounts/login/?next=%2Fp%2FCm1mCdCpSzJ%2F"


@pytest.mark.parametrize(
    "captured",
    [
        pytest.param(page('<html><body><input name="password"></body></html>', final_url=LOGIN_URL), id="login-redirect"),
        # Plain HTTP receives the login page before JavaScript renders its form.
        pytest.param(page("<html><body></body></html>", method="http", final_url=LOGIN_URL), id="redirect-without-form"),
        # Reported in 2026 by yt-dlp and gallery-dl: a redirect to the homepage.
        pytest.param(page("<html><body>Instagram</body></html>", final_url="https://www.instagram.com/"), id="homepage-redirect"),
        # Reported in 2026: the login page served at the post URL, without a redirect.
        pytest.param(page(post_page({"route": {"canonicalRouteName": "comet.igweb.PolarisCAAIGLoginHomepageRoute"}})),
                     id="login-route"),
        # A slow login wall is still a login wall, not a reason to retry.
        pytest.param(page('<html><body><input name="password"></body></html>', final_url=LOGIN_URL,
                          error_kind="timeout", error="Timeout"), id="login-wall-that-timed-out"),
        pytest.param(page("", method="http", http_status=403), id="http-403"),
        pytest.param(page("", method="http", http_status=401), id="http-401"),
    ],
)
def test_login_required(captured):
    analysis = analyze_capture(captured, CODE)
    assert analysis.outcome is FetchOutcome.LOGIN_REQUIRED
    assert not analysis.outcome.post_was_read


def test_post_gated_for_logged_out_visitors():
    # Assumed shape for a gated (e.g. age-restricted) post: the inner post is null. Not yet observed here;
    # ungated posts were seen with "gating_ruling": null and the post inside.
    wrapper = {"code": CODE, "pk": "1001", "id": "1001_1", "gating_ruling": {"gating_type": "18_plus"},
               "if_not_gated_logged_out": None}
    analysis = analyze_capture(page(post_page({"xig_polaris_media": wrapper})), CODE)
    assert analysis.signals.gated_for_logged_out is True
    assert analysis.outcome is FetchOutcome.LOGIN_REQUIRED


@pytest.mark.parametrize(
    "captured",
    [
        pytest.param(page("<html><body>Please wait a few minutes before you try again.</body></html>"), id="message"),
        pytest.param(page("", method="http", http_status=429), id="http-429"),
        pytest.param(page("<html><body></body></html>", network_json=[{"url": "https://www.instagram.com/api/graphql",
                     "status": 200, "body": {"message": "Please wait a few minutes before you try again.", "status": "fail"}}]),
                     id="api-message"),
        pytest.param(page("<html><body></body></html>", network_json=[{"url": "https://www.instagram.com/api/graphql",
                     "status": 200, "body": {"errors": [{"code": 1675004, "severity": "CRITICAL"}]}}]), id="api-code"),
    ],
)
def test_rate_limited(captured):
    assert analyze_capture(captured, CODE).outcome is FetchOutcome.RATE_LIMITED


def test_unrelated_logged_out_api_error_is_not_a_rate_limit():
    # Seen live on every post page: one of the page's own queries is refused; the post still renders.
    body = {"errors": [{"message": "Unauthorized logged out query.", "severity": "CRITICAL", "code": 1675002}]}
    captured = page(post_page(post_data_doc()),
                    network_json=[{"url": "https://www.instagram.com/api/graphql", "status": 200, "body": body}])
    assert analyze_capture(captured, CODE).outcome is FetchOutcome.CAPTION_FOUND


def test_html_comments_are_not_visible_text():
    analysis = analyze_capture(page("<html><body><!-- too many requests --><p>hello</p></body></html>"), CODE)
    assert analysis.signals.rate_limit_message is False


@pytest.mark.parametrize(
    "captured",
    [
        # Seen live on the post page of a missing post (straight apostrophe, in the title and a span).
        pytest.param(page("<html><head><title>Post isn't available • Instagram</title></head>"
                          "<body><span>Post isn't available</span></body></html>"), id="post-page-message"),
        pytest.param(page("<html><body><h2>Sorry, this page isn’t available.</h2></body></html>"), id="curly-apostrophe"),
        # Seen live: a plain HTTP GET of a missing post shows only "Instagram"; the route names the error.
        pytest.param(page(post_page({"route": {"canonicalRouteName": "comet.igweb.PolarisErrorRoute"}}, body="Instagram"),
                          method="http"), id="error-route"),
        # Seen live: the embed view of a missing post.
        pytest.param(page('<html><body><div class="EmbedBrokenMedia"><div>The link to this photo or video may be '
                          "broken, or the post may have been removed.</div></div></body></html>"), id="embed-broken"),
        pytest.param(page("<html><body></body></html>", method="http", http_status=404), id="http-404"),
    ],
)
def test_unavailable(captured):
    analysis = analyze_capture(captured, CODE)
    assert analysis.outcome is FetchOutcome.UNAVAILABLE
    assert not analysis.outcome.post_was_read


@pytest.mark.parametrize(
    ("captured", "outcome"),
    [
        (CapturedPage(method="browser", requested_url=URL, error_kind="timeout", error="Timeout 30000ms exceeded"),
         FetchOutcome.TIMEOUT),
        (CapturedPage(method="http", requested_url=URL, error_kind="network", error="ConnectError"), FetchOutcome.ERROR),
        (CapturedPage(method="browser", requested_url=URL, error_kind="browser", error="Executable doesn't exist"),
         FetchOutcome.ERROR),
        (page("<html><body></body></html>", method="http", http_status=500), FetchOutcome.ERROR),
    ],
)
def test_timeouts_and_errors(captured, outcome):
    assert analyze_capture(captured, CODE).outcome is outcome


def test_unrecognized_page_is_not_reported_as_read():
    analysis = analyze_capture(page("<html><body><div>Something new</div></body></html>"), CODE)
    assert analysis.outcome is FetchOutcome.CAPTION_NOT_FOUND
    assert not analysis.outcome.post_was_read


# --- Robustness against unexpected input ------------------------------------------------------------


@pytest.mark.parametrize(
    "html",
    [
        '<script type="application/json">' + "[" * 50_000 + "]" * 50_000 + "</script>",
        "<script>s.handle({" + json.dumps("contextJSON") + ":" + json.dumps("[" * 50_000 + "]" * 50_000) + "});</script>",
    ],
    ids=["deep-json", "deep-context-json"],
)
def test_absurdly_nested_json_is_ignored_without_crashing(html):
    assert analyze_capture(page(f"<html><body>{html}</body></html>"), CODE).outcome is FetchOutcome.CAPTION_NOT_FOUND


def test_json_prefix_and_newline_delimited_responses():
    body = "for (;;);" + json.dumps({"data": {"items": [{"code": CODE, "pk": "1"}]}})
    assert _decode_json(body)["data"]["items"][0]["code"] == CODE
    assert _decode_json('{"a": 1}\n{"b": 2}') == [{"a": 1}, {"b": 2}]
