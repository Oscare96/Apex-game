import httpx
import pytest

from app.publish import google_session, ig_upload, yt_upload

YT = {
    "channel_id": "channel",
    "client_id": "app",
    "client_secret": "x",
    "refresh_token": "x",
    "privacy": "private",
    "made_for_kids": False,
}
IG = {"account_id": "12", "api_version": "v25.0", "page_id": "11", "page_access_token": "x"}
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test"


def test_resumable_youtube_reconciles_a_lost_receipt(tmp_path):
    clip = tmp_path / "clip"
    clip.write_bytes(b"abcdef")
    calls = []
    state = {}

    def respond(req):
        calls.append(req)
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "x"})
        if req.url.path.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"id": "channel"}]})
        if req.method == "POST":
            return httpx.Response(200, headers={"Location": SESSION})
        if req.headers["Content-Range"] == "bytes */6":
            if any(r.headers.get("Content-Range") == "bytes 2-5/6" for r in calls):
                return httpx.Response(201, json={"id": "received"})
            return httpx.Response(308, headers={"Range": "bytes=0-1"})
        assert req.read() == b"cdef"
        raise httpx.ReadTimeout("injected")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.ReadTimeout):
            yt_upload(client, YT, clip, state, lambda: None, "title", "AI")
        assert state["session"] == SESSION
        assert yt_upload(client, YT, clip, state, lambda: None, "title", "AI") == "received"
        assert sum(r.method == "POST" and r.url.path.endswith("/videos") for r in calls) == 1
        with pytest.raises(RuntimeError, match="identity mismatch"):
            yt_upload(client, {**YT, "channel_id": "wrong"}, clip, {}, lambda: None, "title", "AI")
    with pytest.raises(ValueError):
        google_session("https://example.com/upload/youtube/v3/videos")


def test_instagram_upload_lost_publish_ack(tmp_path):
    clip = tmp_path / "clip"
    clip.write_bytes(b"abcdef")
    state = {}
    calls = []

    def respond(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/me"):
            return httpx.Response(
                200, json={"id": "11", "instagram_business_account": {"id": "12"}}
            )
        if req.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "33"})
        if req.url.host == "rupload.facebook.com":
            assert req.read() == b"abcdef"
            return httpx.Response(200, json={"success": True})
        if req.url.path.endswith("/media_publish"):
            raise httpx.ReadTimeout("injected")
        return httpx.Response(
            200, json={"status_code": "PUBLISHED" if state.get("publish_attempted") else "FINISHED"}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(httpx.ReadTimeout):
            ig_upload(client, IG, clip, state, lambda: None, "title", "AI")
        assert ig_upload(client, IG, clip, state, lambda: None, "title", "AI") == "container:33"
        assert sum(p.endswith("/media_publish") for p in calls) == 1
