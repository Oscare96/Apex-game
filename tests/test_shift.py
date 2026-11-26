import json

import pytest

from app.shift import shift, validate


def test_automatic_shift_retry_and_career_memory(tmp_path):
    plan = {"fares": 1, "publish": []}
    first = shift(tmp_path, "acceptance", plan)
    assert first["complete"] and first["shows"][0]["wins"] == 1
    assert shift(tmp_path, "acceptance", plan) == first
    next_shift = shift(tmp_path, "tomorrow", plan)
    assert next_shift["trained"]["first_seed"] == 5000
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["shows"] == 2 and latest["wins"] == 2
    assert len(list((tmp_path / "shows").glob("*/manifest.json"))) == 2
    with pytest.raises(ValueError, match="configuration changed"):
        shift(tmp_path, "acceptance", {"fares": 2, "publish": []})
    for bad in ({"publish": ["tiktok"]}, {"broadcast": "unknown"}, {"training_episodes": 0}):
        with pytest.raises(ValueError):
            validate(bad)
