"""capture_with_http against a mocked network (httpx2.MockTransport): no real requests."""

import asyncio
import json

import httpx2

from app.importers.instagram import FetchOutcome, analyze_capture, capture_with_http, parse_instagram_url

REF = parse_instagram_url("https://www.instagram.com/p/Cm1mCdCpSzJ/")
CAPTION = "עוגה\n200 גרם קמח\nאופים 25–30 דקות"


def capture(handler) -> object:
    return asyncio.run(capture_with_http(REF.embed_url, transport=httpx2.MockTransport(handler)))


def embed_page(caption: str) -> str:
    """Embed view in the shape seen live: post data as a JSON string inside a script."""
    inner = {"gql_data": {"shortcode_media": {"id": "1", "shortcode": REF.shortcode, "owner": {"username": "baker"},
                                              "edge_media_to_caption": {"edges": [{"node": {"text": caption}}]}}}}
    script = "s.handle({" + json.dumps("contextJSON") + ":" + json.dumps(json.dumps(inner)) + "});"
    return f"<html><body><script>{script}</script></body></html>"


def test_successful_capture_then_analysis():
    captured = capture(lambda request: httpx2.Response(200, text=embed_page(CAPTION)))
    assert (captured.http_status, captured.error_kind) == (200, None)
    assert captured.user_agent.startswith("python-httpx2/")  # the honest default, not a disguise
    analysis = analyze_capture(captured, REF.shortcode)
    assert analysis.outcome is FetchOutcome.CAPTION_FOUND
    assert analysis.best.text == CAPTION


def test_timeout_is_reported_as_timeout():
    def handler(request):
        raise httpx2.ReadTimeout("timed out", request=request)

    captured = capture(handler)
    assert captured.error_kind == "timeout"
    assert analyze_capture(captured, REF.shortcode).outcome is FetchOutcome.TIMEOUT


def test_connection_failure_is_reported_as_error():
    def handler(request):
        raise httpx2.ConnectError("connection refused", request=request)

    captured = capture(handler)
    assert captured.error_kind == "network"
    assert analyze_capture(captured, REF.shortcode).outcome is FetchOutcome.ERROR


def test_redirect_to_login_page():
    def handler(request):
        if request.url.path.startswith("/accounts/login"):
            return httpx2.Response(200, text="<html><body><input name='password'></body></html>")
        return httpx2.Response(302, headers={"Location": "https://www.instagram.com/accounts/login/?next=/p/x/"})

    captured = capture(handler)
    assert captured.final_url.startswith("https://www.instagram.com/accounts/login/")
    assert analyze_capture(captured, REF.shortcode).outcome is FetchOutcome.LOGIN_REQUIRED


def test_whole_request_has_a_deadline():
    # A server that stalls longer than the overall deadline (twice timeout_s).
    async def stall(request):
        await asyncio.sleep(5)
        return httpx2.Response(200, text="late")

    captured = asyncio.run(capture_with_http(REF.embed_url, timeout_s=0.05, transport=httpx2.MockTransport(stall)))
    assert captured.error_kind == "timeout"
    assert captured.elapsed_ms < 2_000


def test_oversized_response_is_refused():
    captured = capture(lambda request: httpx2.Response(200, content=b"x" * 10_000_001))
    assert captured.error_kind == "network"
    assert "larger than" in captured.error
    assert captured.html == ""
