#!/usr/bin/env bash
# Run against the exact worker image intended for the VM.
set -euo pipefail
image=${1:?Pass a local image tag or digest}
volume="apex-accept-$(date +%s)-$$"
docker volume create "$volume" >/dev/null
trap 'docker volume rm "$volume" >/dev/null' EXIT
test "$(docker run --rm --network none "$image" id -u)" = 10001
run=(docker run --rm --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=256m
     --cap-drop ALL --security-opt no-new-privileges -v "$volume:/var/lib/apex" "$image")
for attempt in 1 2; do
  "${run[@]}" python -m app.shift --root /var/lib/apex --config /etc/apex/shift.json --id acceptance
done
"${run[@]}" python -c '
from pathlib import Path
import json
from app.show import verify
root=Path("/var/lib/apex")
markers=sorted(root.glob("shows/*/manifest.json"))
assert len(markers)==3
assert all(verify(p.parent)["wins"] == 1 for p in markers)
journal=json.loads((root/"shifts/acceptance.json").read_text())
assert journal["complete"] and journal["receipts"] == {} and len(journal["shows"])==3
print("Verified 3 wins, media integrity, restart deduplication, and offline execution.")
'
