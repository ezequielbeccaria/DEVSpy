"""Driving a DEVS model step by step from outside, gym-style.

The environment is a water tank: random inflow, an outflow valve set by the
agent, and an observation of the level every time unit. The agent is plain
Python code outside the model: it reads each observation with
`advance(stop_on_output=True)` and answers with `inject("valve", ...)` at the
same instant. A snapshot taken mid-episode lets the agent try two policies from
the same state.
"""

from __future__ import annotations

import random

from devspy import Atomic, Bag, SimulationManager, Digraph

TARGET = 50.0


class Tank(Atomic):
    def __init__(self, seed: int = 0) -> None:
        super().__init__("tank")
        self.add_inport("valve")
        self.add_outport("level")
        self.seed = seed

    def initialize(self) -> None:
        self.rng = random.Random(self.seed)
        self.level = TARGET
        self.valve = 0.5  # fraction open
        self.hold_in("filling", 1.0)

    def deltint(self) -> None:
        inflow = self.rng.uniform(5.0, 15.0)
        self.level = max(0.0, self.level + inflow - 20.0 * self.valve)
        self.hold_in("filling", 1.0)

    def deltext(self, e: float, x: Bag) -> None:
        self.valve = min(1.0, max(0.0, x["valve"][-1]))
        self.cont(e)  # keep the 1.0 period

    def out(self) -> Bag:
        return {"level": [round(self.level, 3)]}


def build(seed: int = 0) -> Digraph:
    env = Digraph("env")
    env.add_inport("valve")
    env.add_outport("level")
    tank = Tank(seed)
    env.add(tank)
    env.add_coupling(env, "valve", tank, "valve")
    env.add_coupling(tank, "level", env, "level")
    return env


def proportional(level: float) -> float:
    return 0.5 + 0.05 * (level - TARGET)


def bang_bang(level: float) -> float:
    return 1.0 if level > TARGET else 0.0


def episode(manager: SimulationManager, policy, steps: int) -> float:
    """Run `steps` observation/action pairs; return the mean absolute error."""
    error = 0.0
    for _ in range(steps):
        [(t, obs)] = manager.advance(stop_on_output=True)
        level = obs["level"][0]
        error += abs(level - TARGET)
        manager.inject("valve", policy(level))  # at time t, e = 0 after the observation
    return error / steps


def run(seed: int = 0, steps: int = 50) -> dict:
    manager = SimulationManager(build(seed))
    episode(manager, proportional, 10)  # warm-up
    checkpoint = manager.snapshot()
    results = {}
    for name, policy in (("proportional", proportional), ("bang-bang", bang_bang)):
        manager.restore(checkpoint)  # both policies start from the same state
        results[name] = episode(manager, policy, steps)
    results["time"] = manager.time
    results["steps"] = steps
    return results


if __name__ == "__main__":
    r = run()
    print(f"from the same checkpoint at t=10, {r['steps']} steps each (ends at t={r['time']}):")
    print(f"  mean |level - {TARGET}| proportional: {r['proportional']:.2f}")
    print(f"  mean |level - {TARGET}| bang-bang   : {r['bang-bang']:.2f}")
