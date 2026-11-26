# Project APEX

APEX is a disclosed, faceless AI gaming character. Its first show, **Night Shift**, follows a taxi driver learning to pick up and deliver passengers in Gymnasium Taxi-v3. The game supplies every observation, action result and score. APEX chooses its own moves, narrates game events with a synthetic voice, streams video, and cuts a vertical highlight.

[Watch a generated highlight](examples/night-shift.mp4) · [Repository audit and research](docs/AUDIT.md) · [Buzz deployment guide](docs/DEPLOY_GOOGLE_CLOUD.md) · [Platform setup](docs/CHANNELS.md) · [Resume the project](docs/BUZZ_HANDOFF.md)

## Run a show locally

Use Linux and Python 3.12. Install FFmpeg with the flite filter and DejaVu Sans fonts. Debian packages are `ffmpeg fonts-dejavu-core`.

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -c deploy/requirements.lock -e '.[show,dev]'
python -m app.shift --config deploy/shift.json --id first-shift
```

This performs the initial 5,000 training episodes, evaluates the learned policy, plays three fares, verifies their replays and writes the recordings under `.apex/shows/`. A shift with the same ID resumes. Subsequent shifts train from the saved policy and keep a candidate only if its validation rank holds up. The shipped configuration runs offline. Start a single paced show with `python -m app.show play --realtime`. Its growing `live.m3u8` plays locally in VLC or ffplay.

## What has been tested

| Capability | Evidence and scope |
|---|---|
| Gameplay and learning | Held-out benchmark over 100 seeds after 5,000 training episodes. Learned policy 100 wins, random policy 1 win, untrained greedy policy 0 wins. Mean learned return 7.62 and 13.38 moves. A separate 100-seed regression set also checks the success threshold. These are results for one fixed game and map. |
| Personality | Authored, event-specific humor. Synthetic speech, synchronized captions and persistent AI identification on both layouts. Career results are available to chat. |
| Broadcast and production | Live HLS segments are available before the fare finishes. H.264/AAC recording, phone-layout highlights, trace replay, file digests and full video decoding run locally. A separate FFmpeg receiver accepted the outbound audio and video over loopback RTMP. |
| Creator operations | Recoverable shifts, one selected highlight per shift per configured destination, account-bound upload sessions and receipts. Twitch title and command replies, YouTube upload and Instagram Reels use official interfaces. Protocol tests use test doubles. Account-level acceptance is open. |
| Hosting | Dedicated Google Compute Engine worker with local persistent state, daily systemd timer, optional chat service and an offline container acceptance script. Buzz owns cloud execution. |

## Engineering checks

```bash
ruff check app tests
pytest -q
docker build -t apex-api:test .
docker build -f Dockerfile.show -t apex-show:test .
bash deploy/container-acceptance.sh apex-show:test
```

The v0.1 driving simulation and private FastAPI endpoints remain available through `docker compose`. Set a random `APEX_API_KEY` in a private `.env` before starting the service. The show worker runs separately. Keep APEX accounts, infrastructure, media and credentials isolated from OwnerEasy.

No retail game integration is enabled. See the handoff for GTA, TikTok, live account acceptance and operational limits. The repository retains the original owner's redistribution terms.
