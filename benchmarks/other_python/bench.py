"""Time other Python DEVS engines on the shared benchmark models.

usage:
  python bench.py ENGINE devstone WIDTH DEPTH EVENTS REPS
  python bench.py ENGINE rl SECTIONS EPISODES HORIZON
ENGINE: xdevs | xdevs-flat | pypdevs-minimal
Prints one JSON line in the same format as ../devstone.py / ../rl_bench.py.
"""
import json
import sys
import time

EPS = 1e-9


def make(engine):
    if engine.startswith("xdevs"):
        from xdevs.sim import Coordinator, SimulationClock
        import xdevs_models as m

        flat = engine == "xdevs-flat"

        def run(model, horizon):
            c = Coordinator(model, SimulationClock(), flatten=flat)
            c.initialize()
            if horizon == float("inf"):
                c.simulate_time()
            else:  # simulate_time is relative to the first event and exclusive
                c.simulate_time(horizon + EPS - c.time_next)
            c.exit()
        return m, run
    if engine == "pypdevs-minimal":
        from pypdevs.minimal import Simulator
        import pypdevs_models as m

        def run(model, horizon):
            s = Simulator(model)
            s.setTerminationTime(horizon + EPS)
            s.simulate()
        return m, run
    raise SystemExit(f"unknown engine {engine}")


def main():
    engine, kind, *args = sys.argv[1:]
    m, run = make(engine)
    if kind == "devstone":
        w, d, n, reps = map(int, args)
        build_ms, sim_ms = [], []
        for _ in range(reps):
            for k in m.STATS:
                m.STATS[k] = 0
            t0 = time.perf_counter()
            model = m.DevStoneTop(w, d, n)
            t1 = time.perf_counter()
            run(model, float("inf"))  # includes simulator setup (+ flattening)
            t2 = time.perf_counter()
            build_ms.append((t1 - t0) * 1e3)
            sim_ms.append((t2 - t1) * 1e3)
        st = {k: m.STATS[k] for k in ("int", "ext", "sink")}
        print(json.dumps({"engine": engine, "w": w, "d": d, "n": n, **st,
                          "build_ms": build_ms, "sim_ms": sim_ms}))
    else:
        sections, episodes, horizon = int(args[0]), int(args[1]), float(args[2])
        t1 = time.perf_counter()
        ep_ms = []
        for ep in range(episodes):
            s = time.perf_counter()
            m.SEED["episode"] = ep
            run(m.RLEnv(sections), horizon)  # no reset in these APIs: rebuild per episode
            ep_ms.append((time.perf_counter() - s) * 1e3)
        t2 = time.perf_counter()
        print(json.dumps({"engine": engine, "sections": sections, "episodes": episodes,
                          "horizon": horizon, "decisions": m.STATS["decisions"],
                          "reward": m.STATS["reward"], "build_ms": 0.0,
                          "run_ms": (t2 - t1) * 1e3, "first_ep_ms": ep_ms[0],
                          "ep_ms_median": sorted(ep_ms)[len(ep_ms) // 2]}))


if __name__ == "__main__":
    main()
