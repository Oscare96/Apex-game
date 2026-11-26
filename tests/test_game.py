from dataclasses import asdict

import gymnasium as gym
import numpy as np
import pytest

from app.game import GAME, HORIZON, evaluate, lock, read_policy, replay, train_and_select, turns


def test_train_reload_replay_and_reject_damage(tmp_path):
    report = train_and_select(tmp_path)
    assert report["promoted"] and report["candidate"]["wins"] >= 90
    assert report["candidate"]["mean_return"] > report["random"]["mean_return"]
    path = tmp_path / "policy.json"
    record, policy = read_policy(path)
    assert evaluate(policy, range(900000, 900100))["wins"] >= 90
    env = gym.make(GAME, max_episode_steps=HORIZON)
    state, _ = env.reset(seed=99)
    trace = [asdict(t) for t in turns(env, state, policy)]
    env.close()
    replay(99, trace)
    with pytest.raises(ValueError):
        replay(99, trace[:-1])
    trace[0]["reward"] += 10
    with pytest.raises(ValueError):
        replay(99, trace)
    train_and_select(tmp_path, 1)
    assert read_policy(path)[0]["next_seed"] == record["next_seed"] + 1
    path.write_text(path.read_text().replace('"game":"Taxi-v3"', '"game":"other"'))
    with pytest.raises(ValueError):
        read_policy(path)


def test_truncation_and_lock(tmp_path):
    assert evaluate(np.zeros((500, 6)), [1])["mean_steps"] == HORIZON
    with lock(tmp_path / "policy.lock"), pytest.raises(RuntimeError):
        train_and_select(tmp_path, 1)
