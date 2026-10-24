"""Time the DEVStone-like model on DEVSpy.

usage: python devstone.py WIDTH DEPTH EVENTS REPS   (prints one JSON line)
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devspy import DevsSuiteFacade  # noqa: E402
from devstone_model import STATS, build  # noqa: E402


def main():
    w, d, n, reps = map(int, sys.argv[1:5])
    build_ms, sim_ms = [], []
    for _ in range(reps):
        for k in STATS:
            STATS[k] = 0
        t0 = time.perf_counter()
        f = DevsSuiteFacade(build(w, d, n))
        f.reset()
        t1 = time.perf_counter()
        f.simulate_to_time(1e18)
        t2 = time.perf_counter()
        build_ms.append((t1 - t0) * 1e3)
        sim_ms.append((t2 - t1) * 1e3)
    print(json.dumps({"engine": "devspy", "w": w, "d": d, "n": n, **STATS,
                      "build_ms": build_ms, "sim_ms": sim_ms}))


if __name__ == "__main__":
    main()
