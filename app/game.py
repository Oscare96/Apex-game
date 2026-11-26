"""Learn, evaluate and play Farama's Taxi-v3 through its public action interface."""

import fcntl
import hashlib
import json
import os
import random
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

import gymnasium as gym
import numpy as np

GAME = "Taxi-v3"
FORMAT = 1
HORIZON = 64
EVAL_SEEDS = range(2**31, 2**31 + 100)
ACTIONS = ("south", "north", "east", "west", "pickup", "dropoff")


@contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another worker owns {path.name}") from error
        yield


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", delete=False) as handle:
        temp = Path(handle.name)
        try:
            json.dump(data, handle, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    os.replace(temp, path)


@dataclass(frozen=True)
class Turn:
    before: int
    action: int
    state: int
    reward: int
    terminated: bool
    truncated: bool


def turns(env, state, q, rng=None):
    while True:
        action = rng.randrange(6) if rng is not None else int(q[state].argmax())
        new, reward, ended, limited, _ = env.step(action)
        yield Turn(int(state), action, int(new), int(reward), bool(ended), bool(limited))
        if ended or limited:
            return
        state = new


def evaluate(q=None, seeds=EVAL_SEEDS):
    env = gym.make(GAME, max_episode_steps=HORIZON)
    wins = total = steps = count = 0
    try:
        for seed in seeds:
            state, _ = env.reset(seed=seed)
            for turn in turns(env, state, q, random.Random(seed) if q is None else None):
                wins += int(turn.terminated)
                total += turn.reward
                steps += 1
            count += 1
    finally:
        env.close()
    return {
        "episodes": count,
        "wins": wins,
        "mean_return": total / count,
        "mean_steps": steps / count,
    }


def train(q, first, count):
    rng = random.Random(first)
    env = gym.make(GAME, max_episode_steps=HORIZON)
    try:
        for seed in range(first, first + count):
            state, _ = env.reset(seed=seed)
            for _ in range(HORIZON):
                action = rng.randrange(6) if rng.random() < 0.25 else int(q[state].argmax())
                new, reward, ended, limited, _ = env.step(action)
                target = reward if ended else reward + 0.95 * q[new].max()
                q[state, action] += 0.4 * (target - q[state, action])
                state = new
                if ended or limited:
                    break
    finally:
        env.close()


def digest(q):
    return hashlib.sha256(q.astype("<f8").tobytes()).hexdigest()


def read_policy(path):
    record = json.loads(path.read_text())
    q = np.array(record["q"], dtype=np.float64)
    if (
        record["format"] != FORMAT
        or record["game"] != GAME
        or q.shape != (500, 6)
        or not np.isfinite(q).all()
        or digest(q) != record["sha256"]
    ):
        raise ValueError("Incompatible or damaged policy")
    return record, q


def train_and_select(root, episodes=5000):
    if not 1 <= episodes <= 50000:
        raise ValueError("Training batch must contain 1 to 50000 episodes")
    with lock(root / "policy.lock"):
        path = root / "policy.json"
        old, q = read_policy(path) if path.exists() else ({}, np.zeros((500, 6)))
        cursor = old.get("next_seed", 0)
        if cursor + episodes > EVAL_SEEDS.start:
            raise ValueError("Training seeds exhausted")
        candidate = q.copy()
        train(candidate, cursor, episodes)
        score = evaluate(candidate)
        incumbent = evaluate(q)
        baseline = evaluate()

        def rank(result):
            return result["wins"], result["mean_return"]

        promote = (
            score["wins"] >= 90 and rank(score) >= rank(incumbent) and rank(score) > rank(baseline)
        )
        report = {
            "training_episodes": episodes,
            "first_seed": cursor,
            "candidate": score,
            "incumbent": incumbent,
            "random": baseline,
            "promoted": promote,
        }
        if promote or old:
            chosen = candidate if promote else q
            save_json(
                path,
                {
                    "format": FORMAT,
                    "game": GAME,
                    "next_seed": cursor + episodes,
                    "sha256": digest(chosen),
                    "q": chosen.tolist(),
                    "last_evaluation": report,
                },
            )
        save_json(root / "benchmark.json", report)
        return report


def replay(seed, trace):
    env = gym.make(GAME, max_episode_steps=HORIZON)
    try:
        state, _ = env.reset(seed=seed)
        if not trace or len(trace) > HORIZON:
            raise ValueError("Invalid replay length")
        for i, row in enumerate(trace):
            new, reward, ended, limited, _ = env.step(row["action"])
            actual = asdict(Turn(int(state), row["action"], int(new), int(reward), ended, limited))
            if actual != row or (ended or limited) != (i == len(trace) - 1):
                raise ValueError(f"Replay mismatch at turn {i + 1}")
            state = new
    finally:
        env.close()
