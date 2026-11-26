"""APEX broadcaster's own Twitch chat and channel metadata via Helix and EventSub."""

import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import websocket

from .game import lock, save_json
from .personality import DISCLOSURE

HELIX = "https://api.twitch.tv/helix"
AUTH = "https://id.twitch.tv/oauth2"
SOCKET = "wss://eventsub.wss.twitch.tv/ws"


def checked(response, expected):
    if response.status_code != expected:
        raise RuntimeError(f"Twitch returned HTTP {response.status_code}")


def login(client, cfg, root, scopes):
    with lock(root / "twitch-oauth.lock"):
        cache = root / "twitch-token.json"
        saved = json.loads(cache.read_text()) if cache.exists() else {}
        token = saved.get("access_token")

        def validate(token):
            return client.get(AUTH + "/validate", headers={"Authorization": "OAuth " + token})

        status = validate(token) if token else None
        if status is not None and status.status_code not in (200, 401):
            checked(status, 200)
        if status is None or status.status_code == 401 or status.json().get("expires_in", 0) < 600:
            response = client.post(
                AUTH + "/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": saved.get("refresh_token", cfg["refresh_token"]),
                    "client_id": cfg["client_id"],
                    "client_secret": cfg["client_secret"],
                },
            )
            checked(response, 200)
            pair = response.json()
            token = pair["access_token"]
            save_json(cache, {"access_token": token, "refresh_token": pair["refresh_token"]})
            status = validate(token)
        checked(status, 200)
        identity = status.json()
        if (
            identity.get("user_id") != cfg["broadcaster_id"]
            or identity.get("client_id") != cfg["client_id"]
            or not scopes.issubset(identity.get("scopes", []))
        ):
            raise RuntimeError("Twitch identity or scope mismatch")
        return {"Client-Id": cfg["client_id"], "Authorization": "Bearer " + token}


def answer(command, root):
    if command in ("!learn", "apex, how did you learn?"):
        return "I practiced pickup and delivery thousands of times. The meter rewards short routes, so I keep the moves that pay off."
    if command in ("!joke", "apex, tell me a joke"):
        return "My passenger asked if I knew a shortcut. I said yes, then took five thousand practice trips."
    if command in ("!apex", "apex, are you human?"):
        return DISCLOSURE + " I learned this taxi route by playing. Ask me !stats or !game."
    if command in ("!game", "apex, what are you playing?"):
        return "I play Gymnasium Taxi. One passenger, four stations, and a meter with no mercy."
    if command in ("!stats", "apex, how are you doing?"):
        path = root / "latest.json"
        if not path.exists():
            return "My first verified shift is still ahead of me."
        last = json.loads(path.read_text())
        return f"My verified record: {last['wins']} fares delivered in {last['shows']} games."
    return None


def claim(db, message, sender, now):
    def hashed(value):
        return hashlib.sha256(value.encode()).hexdigest()

    with db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM replies WHERE stamp < ?", (now - 86400,))
        if db.execute(
            "SELECT 1 FROM replies WHERE stamp>? OR (sender=? AND stamp>?) OR id=? LIMIT 1",
            (now - 10, hashed(sender), now - 60, hashed(message)),
        ).fetchone():
            return False
        db.execute("INSERT INTO replies VALUES(?,?,?)", (hashed(message), hashed(sender), now))
    return True


def event(client, db, headers, owner, root, evt, now):
    if evt.get("broadcaster_user_id") != owner or evt.get("chatter_user_id") in (owner, None):
        return
    reply = answer(evt.get("message", {}).get("text", "").strip().lower(), root)
    if not reply or not evt.get("message_id"):
        return
    if not claim(db, evt["message_id"], evt["chatter_user_id"], now):
        return
    response = client.post(
        HELIX + "/chat/messages",
        headers=headers,
        json={
            "broadcaster_id": owner,
            "sender_id": owner,
            "message": reply,
            "reply_parent_message_id": evt["message_id"],
        },
    )
    checked(response, 200)
    if not any(row.get("is_sent") for row in response.json().get("data", [])):
        print("Twitch declined the reply.", flush=True)


def listen(client, db, headers, owner, root):
    socket = websocket.create_connection(SOCKET, timeout=12, suppress_origin=True)
    deadline = time.monotonic() + 45 * 60
    transfer = False
    try:
        while time.monotonic() < deadline:
            message = json.loads(socket.recv())
            kind = message["metadata"]["message_type"]
            payload = message["payload"]
            if kind == "session_welcome":
                session = payload["session"]
                socket.settimeout((session.get("keepalive_timeout_seconds") or 10) + 5)
                if not transfer:
                    response = client.post(
                        HELIX + "/eventsub/subscriptions",
                        headers=headers,
                        json={
                            "type": "channel.chat.message",
                            "version": "1",
                            "condition": {"broadcaster_user_id": owner, "user_id": owner},
                            "transport": {"method": "websocket", "session_id": session["id"]},
                        },
                    )
                    checked(response, 202)
                transfer = False
            elif kind == "session_reconnect":
                url = payload["session"]["reconnect_url"]
                parsed = urlsplit(url)
                if parsed.scheme != "wss" or not (parsed.hostname or "").endswith(".twitch.tv"):
                    raise ValueError("Invalid reconnect origin")
                new = websocket.create_connection(url, timeout=12, suppress_origin=True)
                socket.close()
                socket = new
                transfer = True
            elif kind == "revocation":
                raise RuntimeError("Twitch revoked the chat subscription")
            elif (
                kind == "notification" and payload["subscription"]["type"] == "channel.chat.message"
            ):
                event(client, db, headers, owner, root, payload["event"], time.time())
    finally:
        socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["chat", "title"])
    parser.add_argument("--root", type=Path, default=Path(".apex"))
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    cfg = json.loads(args.credentials.read_text())
    cfg = cfg.get("twitch", cfg)
    owner = cfg["broadcaster_id"]
    if not isinstance(owner, str) or not owner.isdigit():
        parser.error("Expected APEX broadcaster numeric user ID as a string")
    with lock(root / (args.command + ".lock")), httpx.Client(timeout=8) as client:
        scopes = (
            {"channel:manage:broadcast"}
            if args.command == "title"
            else {"user:read:chat", "user:write:chat"}
        )
        if args.command == "title":
            headers = login(client, cfg, root, scopes)
            response = client.patch(
                HELIX + "/channels",
                params={"broadcaster_id": owner},
                headers=headers,
                json={"title": "APEX | AI taxi driver on the night shift"},
            )
            checked(response, 204)
            return
        db = sqlite3.connect(root / "audience.sqlite")
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS replies(id TEXT PRIMARY KEY,sender TEXT,stamp REAL)"
            )
            while True:
                headers = login(client, cfg, root, scopes)
                listen(client, db, headers, owner, root)
        finally:
            db.close()


if __name__ == "__main__":
    main()
