"""Deterministic bounded synthetic driving simulator; no commercial-game integration."""
from dataclasses import dataclass, asdict
from math import hypot
from random import Random

@dataclass
class State:
    x: float = 0.0
    y: float = 0.0
    speed: float = 0.0
    steps: int = 0
    collisions: int = 0
    finished: bool = False

class DrivingWorld:
    def __init__(self, seed: int = 7):
        rng = Random(seed)
        self.state = State()
        self.target = (30.0, 0.0)
        self.obstacles = [(float(i), rng.choice([-3.0, 3.0])) for i in range(5, 29, 5)]
        self.max_steps = 150

    def observe(self) -> dict:
        return {"state": asdict(self.state), "target": self.target,
                "obstacles": self.obstacles, "remaining": self.max_steps - self.state.steps}

    def step(self, throttle: float, steering: float) -> dict:
        if self.state.finished or self.state.steps >= self.max_steps:
            raise ValueError("Episode has ended")
        throttle = max(-1.0, min(1.0, throttle))
        steering = max(-1.0, min(1.0, steering))
        self.state.speed = max(0.0, min(2.0, self.state.speed + throttle * 0.2))
        self.state.x += self.state.speed
        self.state.y += steering * 0.6
        self.state.steps += 1
        collision = any(hypot(self.state.x - x, self.state.y - y) < 0.8 for x, y in self.obstacles)
        if collision:
            self.state.collisions += 1
            self.state.speed = 0.0
        self.state.finished = self.state.x >= self.target[0] and abs(self.state.y) <= 2.0
        done = self.state.finished or self.state.steps >= self.max_steps
        return {"observation": self.observe(), "reward": (10.0 if self.state.finished else 0.0) - (2.0 if collision else 0.0) - 0.01, "done": done}

class BaselineDriver:
    """Interpretable baseline controller; not reinforcement learning."""
    def action(self, observation: dict) -> tuple[float, float]:
        s = observation["state"]
        obstacles = observation["obstacles"]
        nearby = [(ox, oy) for ox, oy in obstacles if 0 <= ox - s["x"] <= 3.0]
        desired_y = 0.0
        for _, oy in nearby:
            if abs(oy - s["y"]) < 1.5:
                desired_y = -2.0 if oy >= 0 else 2.0
                break
        steer = max(-1.0, min(1.0, (desired_y - s["y"]) * 0.8))
        return (1.0, steer)

def run_episode(seed: int = 7) -> dict:
    world = DrivingWorld(seed)
    driver = BaselineDriver()
    while True:
        throttle, steer = driver.action(world.observe())
        result = world.step(throttle, steer)
        if result["done"]:
            break
    return {"seed": seed, "success": world.state.finished, "steps": world.state.steps,
            "collisions": world.state.collisions, "final_position": [world.state.x, world.state.y]}