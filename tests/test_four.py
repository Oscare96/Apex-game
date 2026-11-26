import json

import pytest

from app import four
from app.show import play, verify


def test_moves_win_tests_blocking_and_replay():
    for stride in (1, 7, 6, 8):
        assert four.won(sum(1 << (19 + i * stride) for i in range(4)))
    assert not four.won((1 << 4) | (1 << 5) | (1 << 7) | (1 << 8))
    mine = sum(1 << (7 * c) for c in range(3))
    assert four.search(mine, 0, 4, -20000, 20000)[1] == 3
    assert four.search(0, mine, 4, -20000, 20000)[1] == 3
    for seed in range(6):
        trace = list(four.moves(seed))
        assert len(trace) <= 42 and four.replay(seed, trace)[1] in (-1, 0, 1)
    trace[2]["column"] = 8
    with pytest.raises(ValueError):
        four.replay(5, trace)


def test_second_game_uses_the_same_broadcast_and_media_verifier(tmp_path):
    path = play(tmp_path, 7, game=four.GAME)
    result = verify(path)
    assert result["game"] == four.GAME and result["policy"] == four.POLICY
    assert result["steps"] == len(json.loads((path / "trace.json").read_text()))
    assert result["script"][0]["text"].startswith(result["disclosure"])
    assert (path / "highlight.mp4").exists() and not (tmp_path / "policy.json").exists()
