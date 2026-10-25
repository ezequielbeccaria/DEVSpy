"""RL-style workload: many short episodes over one reused model (reset per episode).

usage: python rl_bench.py SECTIONS EPISODES HORIZON   (prints one JSON line)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devspy import DevsSuiteFacade  # noqa: E402
from rl_model import SEED, STATS, build  # noqa: E402


def main():
    m, episodes, horizon = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3])
    t0 = time.perf_counter()
    facade = DevsSuiteFacade(build(m))
    t1 = time.perf_counter()
    ep_ms = []
    for ep in range(episodes):
        s = time.perf_counter()
        SEED["episode"] = ep
        facade.reset()
        facade.simulate_to_time(horizon)
        ep_ms.append((time.perf_counter() - s) * 1e3)
    t2 = time.perf_counter()
    print(json.dumps({"engine": "devspy", "sections": m, "episodes": episodes, "horizon": horizon,
                      **STATS, "build_ms": (t1 - t0) * 1e3, "run_ms": (t2 - t1) * 1e3,
                      "first_ep_ms": ep_ms[0], "ep_ms_median": sorted(ep_ms)[len(ep_ms) // 2]}))


if __name__ == "__main__":
    main()
