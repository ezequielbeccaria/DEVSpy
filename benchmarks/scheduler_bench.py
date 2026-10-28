"""Compare the coordinator's schedulers (heap, scan, auto) on dense and sparse
workloads. Appends to results/scheduler.jsonl.

usage: python scheduler_bench.py [--reps N]
"""
import json
import os
import random
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from devspy import Atomic, Digraph  # noqa: E402
try:
    from devspy import SimulationManager
except ImportError:  # DEVSpy < 0.3, when comparing against older checkouts
    from devspy import DevsSuiteFacade as SimulationManager
from devspy.simulation.coordinator import Coordinator  # noqa: E402


class Periodic(Atomic):
    def __init__(self, name, period):
        super().__init__(name)
        self.period = period

    def initialize(self):
        self.hold_in("a", self.period)

    def deltint(self):
        self.hold_in("a", self.period)


def sparse(n):
    """n independent atomics with distinct periods: ~1 imminent per round."""
    rng = random.Random(1)
    g = Digraph("g")
    for i in range(n):
        g.add(Periodic(f"p{i}", 1 + rng.random()))
    return g


def time_run(make, run, reps):
    ts = []
    for _ in range(reps):
        f = SimulationManager(make())
        f.reset()
        t0 = time.perf_counter()
        run(f)
        ts.append((time.perf_counter() - t0) * 1e3)
    return statistics.median(ts)


def main():
    reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 5
    import devstone_model as ds
    import rl_model
    import timeout_model

    def rl(m, episodes):
        def run(f):
            for ep in range(episodes):
                rl_model.SEED["episode"] = ep
                f.reset()
                f.simulate_to_time(200.0)
        return lambda: rl_model.build(m), run

    cases = {
        "devstone 20x20": (lambda: ds.build(20, 20, 500), lambda f: f.simulate_to_time(1e9)),
        "devstone 3x50": (lambda: ds.build(3, 50, 500), lambda f: f.simulate_to_time(1e9)),
        "devstone 200x1": (lambda: ds.build(200, 1, 1000), lambda f: f.simulate_to_time(1e9)),
        "rl m=8 x200": rl(8, 200),
        "rl m=64 x30": rl(64, 30),
        "watchdog 1000": (lambda: timeout_model.build(1000, 0.01, 10), lambda f: f.simulate_to_time(5)),
        "sparse n=64": (lambda: sparse(64), lambda f: f.simulate_iterations(20000)),
        "sparse n=1024": (lambda: sparse(1024), lambda f: f.simulate_iterations(20000)),
        "sparse n=4096": (lambda: sparse(4096), lambda f: f.simulate_iterations(20000)),
    }
    rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                         cwd=HERE).stdout.strip()
    out = open(os.path.join(HERE, "results", "scheduler.jsonl"), "a")
    for name, (make, run) in cases.items():
        row = {"case": name, "rev": rev}
        for mode in ("heap", "scan", "auto"):
            Coordinator.scheduler = mode
            row[mode] = round(time_run(make, run, reps), 2)
        Coordinator.scheduler = "auto"
        print(f"{name:16s} heap={row['heap']:9.1f}  scan={row['scan']:9.1f}  auto={row['auto']:9.1f} ms")
        out.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
