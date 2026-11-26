"""Run one bounded show. A manifest commits its artifacts after replay and media checks."""

import argparse
import hashlib
import json
import random
import secrets
import shutil
import subprocess
import time
import uuid
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import gymnasium as gym

from . import four
from .game import GAME, HORIZON, lock, read_policy, replay, save_json, train_and_select, turns
from .personality import DISCLOSURE
from .studio import STATIONS, broadcast, export_media, frame, portrait, say

SILENCE = ()
FILES = ("trace.json", "episode.mp4", "highlight.mp4", "live.m3u8")
LINES = {
    "pickup": [
        "Seat belt on. My driving instructor is a spreadsheet.",
        "Passenger aboard. Five stars for finding the door.",
    ],
    "dropoff": [
        "Fare delivered. I accept tips in training data.",
        "Made it. The meter and I are both relieved.",
    ],
    "failure": [
        "Shift timed out. That fare deserves a refund.",
        "Time is up. Dispatch is sending me back to class.",
    ],
}


def checksum(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def check_video(path, size):
    cmd = ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
    result = json.loads(subprocess.check_output(cmd, timeout=20))
    streams = result["streams"]
    if not any(s["codec_name"] == "h264" and (s["width"], s["height"]) == size for s in streams):
        raise ValueError(f"Invalid picture in {path.name}")
    if not any(s["codec_name"] == "aac" and s.get("channels", 0) > 0 for s in streams):
        raise ValueError(f"Missing audio in {path.name}")
    duration = float(result["format"]["duration"])
    if duration < 1:
        raise ValueError(f"Truncated media in {path.name}")
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"],
        check=True,
        timeout=120,
    )
    return duration


def media_files(path):
    return sorted([*FILES, *(p.name for p in path.glob("part-*.ts"))])


def result_for(game, seed, trace):
    if game == four.GAME:
        return four.replay(seed, trace)
    if game != GAME:
        raise ValueError("Unknown game")
    replay(seed, trace)
    return int(trace[-1]["terminated"]), sum(t["reward"] for t in trace)


def verify(path, record=None):
    if record is None:
        record = json.loads((path / "manifest.json").read_text())
    if (
        record["game"] not in (GAME, four.GAME)
        or record["format"] != 1
        or record["disclosure"] != DISCLOSURE
    ):
        raise ValueError("Invalid show manifest")
    if set(media_files(path)) != set(record["sha256"]):
        raise ValueError("Incomplete artifact set")
    for name in media_files(path):
        if checksum(path / name) != record["sha256"][name]:
            raise ValueError(f"Artifact digest mismatch: {name}")
    data = json.loads((path / "trace.json").read_text())
    wins, score = result_for(record["game"], record["seed"], data)
    if record["wins"] != wins or record["steps"] != len(data) or record["score"] != score:
        raise ValueError("Score does not match replay")
    hls = (path / "live.m3u8").read_text().splitlines()
    if "#EXT-X-ENDLIST" not in hls or {x for x in hls if x and not x.startswith("#")} != {
        p.name for p in path.glob("part-*.ts")
    }:
        raise ValueError("HLS segments do not match playlist")
    duration = check_video(path / "episode.mp4", (1280, 720))
    highlight = check_video(path / "highlight.mp4", (720, 1280))
    if abs(duration - record["seconds"]) > 0.3 or not 0 < highlight <= duration + 0.25:
        raise ValueError("Media duration disagrees with the show")
    return record


def previous(root):
    for marker in sorted((root / "shows").glob("*/manifest.json"), reverse=True):
        record = json.loads(marker.read_text())
        return {"shows": record["show_number"], "wins": record["career_wins"]}
    return {"shows": 0, "wins": 0}


def taxi_scenes(seed, q):
    rng = random.Random(seed)
    score = 0
    env = gym.make(GAME, max_episode_steps=HORIZON)
    try:
        state, _ = env.reset(seed=seed)
        _, _, passenger, dest = map(int, env.unwrapped.decode(state))
        line = f"{DISCLOSURE} Next fare: {STATIONS[passenger]} to {STATIONS[dest]}."
        yield frame(env, state, None, score, line), line, line, None, False
        aboard = False
        for turn in turns(env, state, q):
            score += turn.reward
            pickup = turn.action == 4 and turn.reward != -10
            aboard |= pickup
            line = None
            if turn.terminated:
                line = rng.choice(LINES["dropoff"])
            elif turn.truncated:
                line = rng.choice(LINES["failure"])
            elif pickup:
                line = rng.choice(LINES["pickup"])
            caption = line or (
                "Taking the fare to " + STATIONS[dest] + " station."
                if aboard
                else "Heading to " + STATIONS[passenger] + " station."
            )
            yield frame(env, turn.state, turn, score, caption), caption, line, asdict(turn), pickup
    finally:
        env.close()


def play(root, seed, realtime=False, on_air=None, feed=None, shift_fare=None, game=GAME):
    root = root.resolve()
    with lock(root / "show.lock"):
        if shutil.disk_usage(root).free < 256 * 1024 * 1024:
            raise RuntimeError("Less than 256 MiB free for media")
        history = previous(root)
        if game == GAME:
            policy_path = root / "policy.json"
            if not policy_path.exists():
                train_and_select(root)
            policy, q = read_policy(policy_path)
            policy_id = policy["sha256"]
            scenes = taxi_scenes(seed, q)
        elif game == four.GAME:
            policy_id = four.POLICY
            scenes = four.scenes(seed)
        else:
            raise ValueError("Unknown game")
        path = (
            root / "shows" / f"{history['shows'] + 1:010d}-{time.time_ns()}-{uuid.uuid4().hex[:8]}"
        )
        path.mkdir(parents=True)
        script = []
        trace = []
        elapsed = 0.0
        highlight_at = None
        with TemporaryDirectory(dir=path) as temp, closing(scenes):
            snapshots = []
            with broadcast(path, realtime, feed) as scene:
                for image, caption, line, turn, highlight in scenes:
                    if line:
                        script.append({"at": round(elapsed, 3), "text": line})
                    if turn:
                        trace.append(turn)
                    if highlight:
                        highlight_at = elapsed
                    shot = Path(temp) / f"turn-{len(snapshots):03}.png"
                    portrait(image, caption).save(shot)
                    duration = scene(image, say(line) if line else SILENCE)
                    snapshots.append((elapsed, duration, shot))
                    elapsed += duration
                    if on_air:
                        on_air(path)
            wins, score = result_for(game, seed, trace)
            save_json(path / "trace.json", trace)
            export_media(
                path,
                highlight_at if highlight_at is not None else max(0, elapsed - 12),
                snapshots,
                elapsed,
            )
        record = {
            "format": 1,
            "game": game,
            "show": path.name,
            "seed": seed,
            "policy": policy_id,
            "shift_fare": shift_fare,
            "show_number": history["shows"] + 1,
            "career_wins": history["wins"] + wins,
            "disclosure": DISCLOSURE,
            "script": script,
            "score": score,
            "steps": len(trace),
            "wins": wins,
            "seconds": round(elapsed, 3),
            "sha256": {name: checksum(path / name) for name in media_files(path)},
        }
        verify(path, record)
        save_json(path / "manifest.json", record)
        save_json(
            root / "latest.json",
            {
                "show": path.name,
                "shows": history["shows"] + 1,
                "wins": history["wins"] + record["wins"],
                "score": score,
                "steps": len(trace),
            },
        )
        return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(".apex"))
    cmd = parser.add_subparsers(dest="command", required=True)
    trainer = cmd.add_parser("train")
    trainer.add_argument("--episodes", type=int, default=5000)
    runner = cmd.add_parser("play")
    runner.add_argument("--game", choices=(GAME, four.GAME), default=GAME)
    runner.add_argument("--seed", type=int, default=None)
    runner.add_argument("--realtime", action="store_true")
    live = cmd.add_parser("broadcast")
    live.add_argument("platform", choices=["twitch-test", "twitch", "youtube"])
    live.add_argument("--credentials", type=Path, required=True)
    live.add_argument("--game", choices=(GAME, four.GAME), default=GAME)
    live.add_argument("--fares", type=int, choices=range(1, 31), default=1)
    verify_cmd = cmd.add_parser("verify")
    verify_cmd.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "train":
        report = train_and_select(args.root, args.episodes)
        print(json.dumps(report))
        if not (args.root / "policy.json").exists():
            parser.exit(1, "No policy cleared the benchmark.\n")
    elif args.command == "broadcast":
        import av

        from .live import LiveFeed, destination

        with lock(args.root / "broadcast.lock"), av.logging.Capture(local=False):
            feed = LiveFeed(destination(args.platform, args.credentials))
            try:
                for _ in range(args.fares):
                    path = play(
                        args.root, secrets.randbelow(2**30), True, feed=feed, game=args.game
                    )
                    print(path, flush=True)
                    if feed.failed:
                        break
            finally:
                feed.close()
            if feed.failed or not feed.frames:
                parser.exit(
                    1,
                    "RTMPS transport failed. Verify the local recording and provider dashboard.\n",
                )
    elif args.command == "verify":
        print(json.dumps(verify(args.directory)))
    else:
        print(
            play(
                args.root,
                secrets.randbelow(2**30) if args.seed is None else args.seed,
                args.realtime,
                game=args.game,
            )
        )


if __name__ == "__main__":
    main()
