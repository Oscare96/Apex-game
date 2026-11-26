"""One autonomous creator shift. A stable ID resumes the same work after interruption."""

import argparse
import hashlib
import json
import re
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

import av
import httpx

from . import four
from .game import GAME, lock, save_json, train_and_select
from .live import HOSTS, LiveFeed, destination
from .publish import deliver
from .show import play, verify
from .twitch import HELIX, checked, login


def validate(plan):
    unknown = set(plan) - {
        "fares",
        "training_episodes",
        "broadcast",
        "publish",
        "twitch_title",
        "games",
    }
    games = plan.get("games", [GAME])
    count = plan.get("fares", 1)
    training = plan.get("training_episodes", 250)
    live = plan.get("broadcast", "off")
    publish = plan.get("publish", [])
    if (
        unknown
        or not isinstance(games, list)
        or not games
        or len(games) > 30
        or any(g not in (GAME, four.GAME) for g in games)
        or type(count) is not int
        or not 1 <= count <= 30
        or type(training) is not int
        or not 1 <= training <= 50000
        or live not in {*HOSTS, "off"}
        or not isinstance(publish, list)
        or any(p not in ("instagram", "youtube") for p in publish)
        or len(set(publish)) != len(publish)
        or type(plan.get("twitch_title", False)) is not bool
    ):
        raise ValueError("Invalid shift configuration")
    return count, training, live, publish


def shift(root, shift_id, plan, credentials=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", shift_id):
        raise ValueError("Invalid shift ID")
    count, training, platform, platforms = validate(plan)
    cfg = json.loads(credentials.read_text()) if credentials else {}
    target = destination(platform, credentials) if platform != "off" and credentials else None
    if platform != "off" and not target:
        raise ValueError("Broadcast credentials required")
    # Freeze account IDs and publication choices. OAuth secrets may rotate between retries.
    contract = {
        "plan": plan,
        "accounts": {
            p: {
                k: v
                for k, v in cfg[p].items()
                if k
                in (
                    "account_id",
                    "channel_id",
                    "page_id",
                    "privacy",
                    "made_for_kids",
                    "title",
                    "description",
                )
            }
            for p in platforms
        },
    }
    if plan.get("twitch_title"):
        contract["twitch_broadcaster_id"] = cfg["twitch"]["broadcaster_id"]
    path = root / "shifts" / (shift_id + ".json")
    with lock(root / "shift.lock"), ExitStack() as resources:
        saved = (
            json.loads(path.read_text())
            if path.exists()
            else {"contract": contract, "shows": [], "receipts": {}}
        )
        if saved["contract"] != contract:
            raise ValueError("Shift configuration changed. Use the recorded contract to resume.")
        if saved.get("complete"):
            return saved

        def checkpoint():
            save_json(path, saved)

        checkpoint()
        client = (
            resources.enter_context(httpx.Client(timeout=30))
            if platforms or plan.get("twitch_title")
            else None
        )
        games = plan.get("games", [GAME])
        if not saved.get("trained") and GAME not in games:
            saved["trained"] = {"strategy": four.POLICY}
            checkpoint()
        if not saved.get("trained"):
            report = train_and_select(root, training if (root / "policy.json").exists() else 5000)
            if not (root / "policy.json").exists():
                raise ValueError("No qualified policy")
            saved["trained"] = report
            checkpoint()
        if plan.get("twitch_title") and not saved.get("title_updated"):
            twitch = cfg["twitch"]
            headers = login(client, twitch, root, {"channel:manage:broadcast"})
            checked(
                client.patch(
                    HELIX + "/channels",
                    params={"broadcaster_id": twitch["broadcaster_id"]},
                    headers=headers,
                    json={"title": "APEX | Autonomous AI game night"},
                ),
                204,
            )
            saved["title_updated"] = True
            checkpoint()
        # A dropped process may have reached viewers. Never replay an uncertain live shift automatically.
        if saved.get("broadcast_state") == "started":
            raise RuntimeError(
                "Previous live transport ended without a receipt. Reconcile in the channel dashboard."
            )
        feed = None
        if target and len(saved["shows"]) < count:
            resources.enter_context(av.logging.Capture(local=False))
            feed = LiveFeed(target)
            saved["broadcast_state"] = "started"
            checkpoint()
        try:
            for i in range(len(saved["shows"]), count):
                seed = int.from_bytes(
                    hashlib.sha256(f"{shift_id}/{i}".encode()).digest()[:4], "big"
                )
                # Find committed local media if a restart occurred before the shift journal advanced.
                key = f"{shift_id}/{i}"
                directory = None
                for manifest in sorted((root / "shows").glob("*/manifest.json"), reverse=True):
                    if json.loads(manifest.read_text()).get("shift_fare") == key:
                        directory = manifest.parent
                        break
                if directory is None:
                    directory = play(
                        root,
                        seed,
                        realtime=bool(feed),
                        feed=feed,
                        shift_fare=key,
                        game=games[i % len(games)],
                    )
                record = verify(directory)
                saved["shows"].append(
                    {
                        "directory": directory.name,
                        "score": record["score"],
                        "wins": record["wins"],
                        "game": record["game"],
                    }
                )
                checkpoint()
                if feed and feed.failed:
                    break
        finally:
            if feed:
                feed.close()
        if feed:
            if feed.failed or not feed.frames:
                raise RuntimeError(
                    "Live transport failed. Local media retained. Reconcile before another broadcast."
                )
            saved["broadcast_state"] = "encoder_finished"
            checkpoint()
        titles = list(dict.fromkeys(s.get("game", GAME) for s in saved["shows"]))
        try:
            day = datetime.strptime(shift_id, "%Y-%m-%d").date().toordinal()
        except ValueError:
            day = int.from_bytes(hashlib.sha256(shift_id.encode()).digest()[:4], "big")
        featured = titles[day % len(titles)]
        pool = [s for s in saved["shows"] if s.get("game", GAME) == featured]
        best = max(pool, key=lambda s: (s["wins"], s["score"]))
        saved["featured_show"] = best["directory"]
        directory = root / "shows" / best["directory"]
        failures = []
        for name in platforms:
            if name in saved["receipts"]:
                continue
            try:
                saved["receipts"][name] = deliver(root, directory, name, cfg[name], client)
                checkpoint()
            except (httpx.HTTPError, RuntimeError, ValueError, KeyError) as error:
                failures.append(name)
                print(f"{name} delivery needs attention ({type(error).__name__}).", flush=True)
        if failures:
            raise RuntimeError("Resume this shift for: " + ", ".join(failures))
        saved["complete"] = True
        checkpoint()
        return saved


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--root", type=Path, default=Path(".apex"))
    cli.add_argument("--config", type=Path, required=True)
    cli.add_argument("--credentials", type=Path)
    cli.add_argument("--id", default=datetime.now(UTC).date().isoformat())
    args = cli.parse_args()
    result = shift(args.root, args.id, json.loads(args.config.read_text()), args.credentials)
    print(
        json.dumps(
            {
                "id": args.id,
                "complete": result["complete"],
                "shows": result["shows"],
                "receipts": result["receipts"],
            }
        )
    )


if __name__ == "__main__":
    main()
