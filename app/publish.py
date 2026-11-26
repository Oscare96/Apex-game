"""Deliver a verified highlight to a configured creator account using official APIs."""

import argparse
import hashlib
import json
import re
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .game import lock, save_json
from .show import verify


class Deferred(RuntimeError):
    def __init__(self, deadline):
        self.deadline = deadline
        super().__init__("Provider requested a later attempt")


def retry_deadline(response):
    value = response.headers.get("Retry-After", "").strip()
    now = time.time()
    if value.isdecimal():
        return now + max(1, int(value))
    if value:
        try:
            return max(now + 1, parsedate_to_datetime(value).timestamp())
        except (TypeError, ValueError, OverflowError):
            pass
    return now + 900


def expect(response, *codes):
    if response.status_code == 429 or (
        response.status_code == 503 and "Retry-After" in response.headers
    ):
        raise Deferred(retry_deadline(response))
    if response.status_code not in codes:
        raise RuntimeError(f"Provider returned HTTP {response.status_code}. Retain delivery state.")
    return response


def google_session(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "www.googleapis.com"
        or parts.path != "/upload/youtube/v3/videos"
    ):
        raise ValueError("Unexpected Google upload location")
    return url


def yt_upload(client, cfg, file, state, persist, title, description):
    channel = cfg["channel_id"]
    privacy = cfg["privacy"]
    if (
        privacy not in {"private", "unlisted", "public"}
        or not 1 <= len(title) <= 100
        or len(description.encode()) > 5000
    ):
        raise ValueError("Invalid YouTube metadata or privacy selection")
    if type(cfg["made_for_kids"]) is not bool:
        raise ValueError("Select the correct YouTube audience")
    result = expect(
        client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "refresh_token": cfg["refresh_token"],
                "grant_type": "refresh_token",
            },
        ),
        200,
    )
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    accounts = expect(
        client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"mine": "true", "part": "id"},
            headers=headers,
        ),
        200,
    ).json()
    if [row["id"] for row in accounts["items"]] != [channel]:
        raise RuntimeError("YouTube channel identity mismatch")
    size = file.stat().st_size
    if "session" not in state:
        resp = expect(
            client.post(
                "https://www.googleapis.com/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"},
                headers={
                    **headers,
                    "X-Upload-Content-Length": str(size),
                    "X-Upload-Content-Type": "video/mp4",
                },
                json={
                    "snippet": {"title": title, "description": description, "categoryId": "20"},
                    "status": {
                        "privacyStatus": privacy,
                        "selfDeclaredMadeForKids": cfg["made_for_kids"],
                        "containsSyntheticMedia": True,
                    },
                },
            ),
            200,
            201,
        )
        state["session"] = google_session(resp.headers["Location"])
        persist()
    session = google_session(state["session"])
    probe = client.put(
        session, headers={**headers, "Content-Range": f"bytes */{size}", "Content-Length": "0"}
    )
    expect(probe, 200, 201, 308)
    if probe.status_code != 308:
        return probe.json()["id"]
    received = probe.headers.get("range")
    offset = 0
    if received:
        match = re.fullmatch(r"bytes=0-(\d+)", received)
        if not match:
            raise ValueError("Malformed upload progress")
        offset = int(match[1]) + 1
    if offset >= size:
        raise RuntimeError("YouTube has all bytes. Reconcile the session status.")
    with file.open("rb") as body:
        body.seek(offset)
        response = client.put(
            session,
            headers={
                **headers,
                "Content-Type": "video/mp4",
                "Content-Length": str(size - offset),
                "Content-Range": f"bytes {offset}-{size - 1}/{size}",
            },
            content=iter(lambda: body.read(256 * 1024), b""),
        )
    expect(response, 200, 201)
    return response.json()["id"]


def ig_upload(client, cfg, file, state, persist, title, description):
    account = cfg["account_id"]
    version = cfg["api_version"]
    if not (account.isdigit() and re.fullmatch(r"v[0-9]+\.0", version)):
        raise ValueError("Invalid Instagram account or API version")
    base = "https://graph.facebook.com/" + version
    headers = {"Authorization": "Bearer " + cfg["page_access_token"]}
    page = expect(
        client.get(
            base + "/me", params={"fields": "id,instagram_business_account{id}"}, headers=headers
        ),
        200,
    ).json()
    if (
        page.get("id") != cfg["page_id"]
        or (page.get("instagram_business_account") or {}).get("id") != account
    ):
        raise RuntimeError("Instagram professional account identity mismatch")
    if "container" not in state:
        result = expect(
            client.post(
                f"{base}/{account}/media",
                headers=headers,
                data={
                    "media_type": "REELS",
                    "upload_type": "resumable",
                    "caption": title + "\n" + description,
                },
            ),
            200,
        ).json()
        state["container"] = result["id"]
        persist()
    container = state["container"]
    if not isinstance(container, str) or not container.isdigit():
        raise ValueError("Invalid Instagram container ID")
    if not state.get("uploaded"):
        with file.open("rb") as body:
            result = client.post(
                f"https://rupload.facebook.com/ig-api-upload/{version}/{container}",
                headers={
                    "Authorization": "OAuth " + cfg["page_access_token"],
                    "offset": "0",
                    "file_size": str(file.stat().st_size),
                    "Content-Type": "application/octet-stream",
                },
                content=iter(lambda: body.read(256 * 1024), b""),
            )
        if not expect(result, 200).json().get("success"):
            raise RuntimeError("Instagram upload needs reconciliation")
        state["uploaded"] = True
        persist()
    for attempt in range(5):
        status = expect(
            client.get(f"{base}/{container}", params={"fields": "status_code"}, headers=headers),
            200,
        ).json()["status_code"]
        if status == "PUBLISHED":
            # Recover acknowledgement when the previous publish response was lost.
            return "container:" + container
        if status == "FINISHED":
            if state.get("publish_attempted"):
                raise RuntimeError("Reconcile the previous Instagram publish before resubmission")
            state["publish_attempted"] = True
            persist()
            raw = client.post(
                f"{base}/{account}/media_publish", headers=headers, data={"creation_id": container}
            )
            if raw.status_code == 429:
                state.pop("publish_attempted")
                persist()
            response = expect(raw, 200)
            return response.json()["id"]
        if status != "IN_PROGRESS":
            raise RuntimeError("Instagram processing stopped: " + status)
        if attempt < 4:
            time.sleep(60)
    raise RuntimeError("Instagram is still processing. Resume this delivery.")


def deliver(root, directory, platform, cfg, client):
    record = verify(directory)
    file = directory / "highlight.mp4"
    clip = record["sha256"][file.name]
    account = cfg["channel_id"] if platform == "youtube" else cfg["account_id"]
    identity = hashlib.sha256(f"{platform}:{account}:{clip}".encode()).hexdigest()
    path = root / "deliveries" / (identity + ".json")
    with lock(path.with_suffix(".lock")):
        state = (
            json.loads(path.read_text())
            if path.exists()
            else {"platform": platform, "account": account, "clip": clip}
        )
        if state.get("remote_id"):
            return state["remote_id"]

        def persist():
            save_json(path, state)

        if "title" not in state:
            state["title"] = cfg.get(
                "title", f"APEX game night #{record['show_number']} | {record['game']}"
            )
            state["description"] = cfg.get(
                "description", record["disclosure"] + f" Game score: {record['score']}."
            )
            if record["disclosure"] not in state["description"]:
                state["description"] = record["disclosure"] + " " + state["description"]
            persist()
        if state.get("retry_after", 0) > time.time():
            raise Deferred(state["retry_after"])
        upload = yt_upload if platform == "youtube" else ig_upload
        try:
            receipt = upload(
                client, cfg, file, state, persist, state["title"], state["description"]
            )
        except Deferred as error:
            state["retry_after"] = error.deadline
            persist()
            raise
        if not isinstance(receipt, str) or not receipt:
            raise ValueError("Missing provider receipt")
        state["remote_id"] = receipt
        state.pop("session", None)
        persist()
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["youtube", "instagram"])
    parser.add_argument("show", type=Path)
    parser.add_argument("--root", type=Path, default=Path(".apex"))
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads(args.credentials.read_text())[args.platform]
    try:
        with httpx.Client(timeout=30) as client:
            print(deliver(args.root, args.show, args.platform, cfg, client))
    except httpx.RequestError:
        parser.exit(1, "Network error. Resume with the same state and clip.\n")


if __name__ == "__main__":
    main()
