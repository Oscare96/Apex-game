import json
import sqlite3

import av
import httpx
import pytest

from app.live import LiveFeed, destination
from app.show import play
from app.twitch import event, login


def test_real_broadcast_mux_matches_completed_game(tmp_path):
    feed = LiveFeed(str(tmp_path / "transport.flv"))
    path = play(tmp_path, 7, feed=feed)
    feed.close()
    assert not feed.failed and feed.frames > 100
    with av.open(str(tmp_path / "transport.flv")) as result:
        assert {s.type for s in result.streams} == {"video", "audio"}
        assert sum(1 for _ in result.decode(video=0)) == feed.frames
    assert (
        abs(json.loads((path / "manifest.json").read_text())["seconds"] - feed.frames / 30) < 0.02
    )


def test_platform_destination_and_key_validation(tmp_path):
    cfg = tmp_path / "credentials"
    cfg.write_text('{"twitch_stream_key":"test_only_key"}')
    assert destination("twitch-test", cfg).endswith("?bandwidthtest=true")
    assert "?" not in destination("twitch", cfg)
    cfg.write_text('{"twitch_stream_key":"not/a/key"}')
    with pytest.raises(ValueError):
        destination("twitch", cfg)


def test_chat_reply_claim_and_scope_validation(tmp_path):
    calls = []

    def responder(req):
        calls.append(req.url.path)
        if req.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "test", "refresh_token": "rotated"})
        if req.url.path.endswith("/validate"):
            return httpx.Response(
                200,
                json={
                    "user_id": "12",
                    "client_id": "app",
                    "expires_in": 3600,
                    "scopes": ["user:write:chat", "user:read:chat"],
                },
            )
        return httpx.Response(200, json={"data": [{"is_sent": True}]})

    cfg = {
        "broadcaster_id": "12",
        "client_id": "app",
        "refresh_token": "test",
        "client_secret": "test",
    }
    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        headers = login(client, cfg, tmp_path, {"user:read:chat"})
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE replies(id TEXT PRIMARY KEY,sender TEXT,stamp REAL)")

        def send(mid, who, txt, now, owner="12"):
            event(
                client,
                db,
                headers,
                "12",
                tmp_path,
                {
                    "chatter_user_id": who,
                    "message_id": mid,
                    "broadcaster_user_id": owner,
                    "message": {"text": txt},
                },
                now,
            )

        send("a", "77", "!stats", 100)
        send("a", "77", "!stats", 200)
        send("b", "77", "!game", 115)
        send("c", "78", "!game", 105)
        send("d", "12", "!apex", 300)
        send("e", "77", "repeat my text", 300)
        send("f", "77", "!game", 300, "99")
        send("g", "78", "!game", 301)
        assert calls.count("/helix/chat/messages") == 2
        with pytest.raises(RuntimeError, match="identity or scope"):
            login(client, cfg, tmp_path, {"channel:manage:broadcast"})
