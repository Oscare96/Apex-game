import json

import numpy as np
import pytest

from app.show import play, verify
from app.studio import say


def test_live_fragments_before_completion_and_rendered_content(tmp_path):
    observed = []

    def observe(path):
        playlist = path / "live.m3u8"
        if playlist.exists() and not observed:
            parts = playlist.read_text().splitlines()
            first = next(line for line in parts if line and not line.startswith("#"))
            assert (path / first).stat().st_size > 0
            assert "#EXT-X-ENDLIST" not in parts
            assert not (path / "manifest.json").exists()
            observed.append(first)

    path = play(tmp_path, 7, on_air=observe)
    assert observed
    record = verify(path)
    assert record["wins"] == 1 and record["steps"] > 1
    assert record["script"][0]["text"].startswith(record["disclosure"])
    assert len(record["script"]) == 3
    assert json.loads((tmp_path / "latest.json").read_text())["show"] == path.name
    assert np.max(np.abs(say(record["script"][1]["text"]))) > 100
    (path / observed[0]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify(path)
