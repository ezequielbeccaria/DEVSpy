# Performance

All numbers were measured on an AMD Ryzen 7 5700X (8C/16T) with Linux 6.8.
The reference interpreter is CPython 3.12, and every engine runs **the same
model** with matching counters, so the work done is identical. Raw data is in
`benchmarks/results/*.jsonl`, and the methodology and every result are in
[`benchmarks/FINDINGS.md`](../benchmarks/FINDINGS.md). Lower is better unless
noted.

## DEVStone (ms, warm median)

The model is a DEVStone-LI-like hierarchy, width × depth.

| Engine | 5×3 | 10×10 | 200×1 | 3×50 | 20×20 |
|---|---|---|---|---|---|
| DEVSpy 0.1 (before this work) | 154 | 996 | 1480 | 2223 | 2011 |
| **DEVSpy 0.3** | **22.9** | **135** | **286** | **77.5** | **278** |
| DEVSpy 0.3 on CPython 3.14 | 19.5 | 106 | 222 | 61.9 | 217 |
| DEVSpy 0.3 on PyPy 3.11 | 13.5 | 42.8 | 84.7 | 27.5 | 93.1 |
| PythonPDEVS (minimal kernel) | 28 | 154 | 333 | 90 | 325 |
| xDEVS.py (flattened) | 65 | 381 | 863 | 231 | 803 |
| DEVSJAVA (tuned JVM) | 61 | 307 | 492 | 567 | 583 |
| adevs (C++) | 3 | 25 | 53 | 25 | 70 |
| Cadmium v2 (C++) | 1 | 7 | 12 | 6 | 15 |

## RL-shaped workload

The model has M track sections and an agent that decides at every arrival.
Episodes are short, with `reset()` between them.

| Engine | M=8, ms/episode | M=64, ms/episode | 16 workers, episodes/s (total RSS) |
|---|---|---|---|
| **DEVSpy 0.3** | **2.95** | **22.7** | **3071** (210 MiB) |
| DEVSpy 0.3 on CPython 3.14 | 2.61 | 18.6 | 3376 (267 MiB) |
| DEVSpy 0.3 on PyPy 3.11 | 0.76 (first episode 27) | 5.6 | 2977 (1.2 GiB) |
| PythonPDEVS (minimal) | 4.55 | 31.7 | 1926 |
| DEVSJAVA (tuned) | 5.11 | 179 | 540 (2.3 GiB) |
| adevs (C++) | 0.44 | 15.0 | n/a |

On a real application, an RLDEVSpy-TrackRailway episode with 5 trains, the
time went from 333 ms (0.1) to about 109 ms, with identical trajectories.

## What made it fast

The changes, in order of effect:

1. The coupling hierarchy is flattened at construction into direct
   atomic-to-atomic routes, with a heap of next event times. Only imminent
   models and receivers are touched in each round.
2. Messages are plain dict bags: no `Message`/`Content`/entity wrappers.
3. The scheduler is adaptive: a linear scan replaces the heap for dense
   networks (−16% on DEVStone).
4. The heap is compacted when stale entries pile up. This made RL 14–17%
   faster and keeps watchdog-style models bounded.
5. Quick wins: logging guarded by `is_enabled`, `__slots__`, and reading
   `sigma` directly when `ta()` is not overridden.

Some ideas were measured and rejected, among them mypyc, disabling the GC,
splitting root routes out of λ, and delivering bags without copying them.
FINDINGS records the reasons.

## Interpreters

- **CPython 3.13** performs the same as 3.12.
- **CPython 3.14** is 14–21% faster with no changes, so it is the recommended
  version.
- **PyPy** is 3–4× faster in steady state, within 1.1–1.7× of adevs on
  DEVStone. It pays for that with JIT warmup and 6–7× the memory, so it suits
  long single-process runs. It cannot run PyTorch/NumPy-based RL stacks.

## Writing fast models

- Most time in real applications is spent in the models. Emit events only
  when something changes, rather than on every tick.
- In hot transition code, use `self.phase == "busy"` rather than
  `self.phase_is("busy")`.
- Don't override `ta()` unless you need to: the kernel reads `sigma` directly.
- Keep `out()` cheap. It runs for every imminent model in every round.
