# Project APEX recovery handoff

## Recover the code

The source of truth is `Oscare96/Apex-game`, branch `main`. Start a new chat with the repository URL, this file and the exact SHA of the new deployment, if any. Fetch the current Git reference. The Git log is the checkpoint ledger. Cloud activation and real social account acceptance are owned by Buzz. No project ID, account linkage, live stream or production deployment has been verified by the implementation session.

```bash
git clone https://github.com/Oscare96/Apex-game.git
cd Apex-game
git status --short --branch
git log --first-parent --oneline -12
git fsck --full
```

Read [the audit](AUDIT.md), [the GCP runbook](DEPLOY_GOOGLE_CLOUD.md) and [the channel setup](CHANNELS.md). Reproduce the README checks on Linux with Python 3.12. Inspect the latest GitHub Actions run for the selected SHA, including both image builds and the offline container acceptance step. New work belongs in tested commits on this repository.

## Checkpoints

| Baseline or batch | What to inspect |
|---|---|
| `f654212` recovered | Synthetic driving research API. Six tests. Audit found identical scores on 1,000 seeds; original lint failed. |
| `e940892` research | Inventory, measurements, architecture candidates and formal game boundaries. |
| `ffa3898` gameplay | Taxi-v3 learning, policy digests, withheld evaluation, disjoint training seed cursor, traces and replay. |
| `20dfa83` media | Real speech, HLS during gameplay, landscape episodes, highlight extraction and integrity checks. |
| `d80ccff` live and audience | RTMPS encoder for Twitch and YouTube, explicit Twitch bandwidth test, own-account OAuth validation and EventSub chat. |
| `24216cd` publishing | Resumable YouTube and Instagram clips, recovery receipts and contract tests. |
| `8d40923` operations | Durable shift IDs, per-platform receipts, dedicated worker image, native phone layout, timer, pinned worker dependencies and container acceptance. |
| Current tip | Deployment and provider instructions, acceptance evidence and the example highlight. The live transport sends an AI-disclosed intermission while the recording is verified, then returns to the next fare. Scheduled shifts retry failed work within a bounded window and upload journals retain provider backoff deadlines. The additional wire test plays a complete game into a real local FFmpeg RTMP receiver and checks both streams and the received frame count. Use the exact live branch SHA. |

## Runtime state

| Path under `/var/lib/apex` | Recovery meaning |
|---|---|
| `policy.json`, `benchmark.json` | Compatible incumbent Q table, digest, training cursor and latest benchmark. Inference uses only the promoted table. Damaged policies stop the run. |
| `shows/<id>/manifest.json` | Completion marker written after replay, media decode and checksums. Directories without it are incomplete and are ineligible for publishing. |
| `shows/<id>/trace.json` and media | Every action, observation, reward, termination or timeout; playlist, HLS segments, recording and generated highlight. |
| `shifts/<id>.json` | Frozen shift configuration, completed fares, selected destination receipts and transport state. A live attempt marked started requires provider reconciliation after interruption. |
| `deliveries/` | Sensitive resumable session or container state and confirmed remote IDs keyed by destination, account and clip digest. Preserve on rollback. |
| `latest.json`, `audience.sqlite` | Latest completed shift statistics and a bounded chat reply ledger. The ledger stores hashed IDs and timestamps; it contains no message text. |
| `twitch-token.json` | Rotated Twitch OAuth credentials. Restrict access to the worker and snapshots. |

On the VM, load the accepted image tag and verify the latest complete show without outbound networking.

```bash
IMAGE=$(sudo sed -n 's/^APEX_IMAGE=//p' /etc/apex/worker.env)
SHOW=$(sudo python3 -c 'import json; print(json.load(open("/var/lib/apex/latest.json"))["show"])')
sudo docker run --rm --network none --read-only --tmpfs /tmp \
  -v /var/lib/apex:/var/lib/apex:ro "$IMAGE" \
  python -m app.show verify "/var/lib/apex/shows/$SHOW"
```

After an unclean stop, inspect the latest manifest even if `latest.json` predates it. Shift recovery locates completed fares by shift ID and fare index. Compare any unfinished outbound operation with the provider before replaying it. Protect both the disk snapshot and the accepted release identifier.

## Open work and acceptance owners

| Item | Current status / required evidence |
|---|---|
| Google Cloud | Buzz must supply the dedicated billed project, IAM, region and zone; run offline acceptance on the VM; record disk restore, rollback, cost and timer evidence. |
| External accounts | Buzz must supply APEX-specific credentials, scopes, eligible accounts and an approved posting cadence. Follow the platform-specific tests. Remote channel playback, replies, post visibility, 24-hour stability and stream reconnect under loss remain unverified. |
| GTA or any retail title | No supported interface or authorization for the proposed automated use was established. Capture rights, automation permission, licensing and supported environment must be verified for each title first. |
| TikTok | Unattended internal posting conflicts with current Direct Post requirements. Vertical exports are ready for creator review. |
| Personality and games | Taxi is the first learned game. The original driving simulator also runs. The character uses authored event-driven humor and command-based Twitch replies. Open-ended dialogue, game-independent visual control, long-form show direction and additional authorized games remain future work. |
| OwnerEasy | No production systems or customer data were accessed. Shared design ideas include replayable media jobs, disclosure and durable publishing receipts. A future integration needs an independently versioned contract and separate APEX credentials. |

For the next engineering batch, use the first real private broadcast and restore drill to measure audio/video drift, session continuity between fares, CPU usage, storage per hour and approved monthly spend. Attach measured results to the deployed SHA.
