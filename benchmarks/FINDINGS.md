# Findings log

Raw data is in `results/*.jsonl` and the generated tables in `results/SUMMARY.md`.
Preliminary runs, kept for traceability, are in `results/archive/prelim/`.
Everything was measured on an AMD Ryzen 7 5700X (8C/16T) with Linux 6.8,
CPython 3.12.3, OpenJDK 17 and g++ 13.3 (`-O2`).

Labels used in the tables:

| Label | Engine |
|---|---|
| `devspy@0857ff6` | DEVSpy before this work (baseline) |
| `devspy@eb23a82` | DEVSpy with the quick wins |
| `devspy[devspy-mypyc]` | Quick wins, with `devspy.simulation` compiled by mypyc 2.4.0 |
| `devsjava` | Devs-Suite-Facade `d8c4917` (DEVSJAVA 2.7 core) on JDK 17 defaults. `[...]` lists the JVM flags |
| `xdevs`, `xdevs-flat` | xDEVS.py 3.0.0 (PyPI), hierarchical and with `flatten=True` |
| `pypdevs-minimal` | PythonPDEVS 2.4.1 minimal kernel (github.com/capocchi/PythonPDEVS), converted with lib2to3 |
| `adevs` | adevs `ee9fed9` (github.com/smiz/adevs), C++ |
| `cadmium` | Cadmium v2 `f0f3ed2` (github.com/SimulationEverywhere/cadmium_v2), C++ |

## Methodology

- **Same models everywhere.** There are two models.
  - DEVStone-like LI: a generator feeding a W×D hierarchy into a sink.
  - RL-shaped: M track sections plus an agent atomic that decides the dwell
    time at every arrival, with `reset()` per episode and integer arithmetic
    driven by a shared LCG.

  Each port prints counters, and these must match the DEVSpy run exactly.
  - DEVStone: internal and external transitions, plus messages received by the
    sink.
  - RL: decisions taken and total reward.

  They match for every engine except PythonPDEVS in the RL model (see
  "Semantic differences").
- **API differences** that are neutral for these models are documented at the
  top of each port. For example, xDEVS, adevs, Cadmium and PythonPDEVS call
  `deltext(0)` inside the default `deltcon`, and several engines stop at
  `t < end` instead of `t <= end`.
- **Timing.**
  - `sim_ms` is in-process and excludes building the model. Engines that
    flatten or create simulators at start-up include that cost.
  - The warm median skips the first rep, which is the JIT warm-up for Java.
  - "Process" columns measure the whole OS process. RSS comes from
    `/usr/bin/time` (`ru_maxrss` from `wait4` in Python would include the forked
    parent's ~14 MiB).
- **RL.** DEVSpy and DEVSJAVA reuse the model and call `reset()`. The other
  engines have no reset API (xDEVS's `initialize()` rebuilds its tree;
  PythonPDEVS-minimal has no initialize), so they rebuild the model per
  episode.

## Iteration 1: quick wins (PR #2, branch `perf/quick-wins`)

### Baseline profile (DEVSpy `0857ff6`, DEVStone 20×20)

| Hotspot | Share |
|---|---|
| `Coordinator.next_tn`, which recomputes `min` recursively over the whole tree every step | ~20% |
| `Atomic.show_state`, which builds 2 f-strings and makes a `logging` call per transition even when logging is off | ~12% |
| Coordinator loops that call `compute_input_output` / `delt_func` on every child | most of the remaining per-step overhead |

DEVSJAVA has the same O(N)-per-step structure. It reaches the children via
reflection (`ensembleBag.tellAll`) and builds a `TreeSet` of every child's
`tN` on each step. Its JIT hides much of that cost.

### Changes

1. `util.logging.is_enabled(level)`. Disabled levels no longer format
   strings. `show_state` is only called when the model overrides it or logging
   is on.
2. `Coordinator.next_tn` is now `min(child.t_n)`, with no recursion.
3. λ runs only on imminent children (`t_n == t`). δ runs only on children that
   are imminent or have input.

### Formal validation (Parallel DEVS abstract simulator, Chow & Zeigler 1994)

- **(2)** The coupled model's `tN = min_{d∈D} tN_d` is unchanged by definition.
  Only how it is computed changes, and that relies on the invariant that each
  child's `t_n` is current after `initialize`/`wrap_deltfunc`.
- **(3a)** The `@`-message (compute output) goes to `IMM(t) = {d | tN_d = t}`
  only. A non-imminent component has no output at `t`. The old code called it
  and got an empty bag back.
- **(3b)** The `*`-message (transition) goes to `IMM(t) ∪ INF(t)`. Any other
  component keeps `s` and `tL`, so its elapsed time keeps growing. The old code
  already skipped δ for atomics. On a no-op round it set `tL := t` on nested
  coordinators, a value nothing reads, and the new code leaves it untouched as
  the abstract simulator prescribes.
- **(1)** No semantic content.

**Empirical check.** `trace_diff.py` records every λ and δ for 206 models: the
3 examples, 3 DEVStone shapes and 200 random hierarchical models with depth up
to 4, ties, `ta = 0` and confluence. That is ~30k simulator-level events,
including 2,959 confluent transitions and 143 models with simultaneous external
events at `e = 0`. The baseline and quick-wins traces are **byte-identical**
(`ALL 2acb222159b348e8`). The model-level trace (`--model-level`, 48,617
events) is identical for baseline, quick wins and mypyc
(`ALL 15d10eaa9bab169e`).

Downstream, RLDEVSpy-TrackRailway gives 106 passed and 4 failed both before
and after. The 4 failures in `tests/env/test_invariants.py` predate this work.

### DEVStone-like: simulation wall clock (ms, warm median)

| config | DEVSpy base | DEVSpy quick wins | DEVSpy + mypyc | DEVSJAVA | DEVSJAVA tuned¹ | xDEVS | xDEVS flat | PyPDEVS-min | adevs | Cadmium |
|---|---|---|---|---|---|---|---|---|---|---|
| 5×3, 1000 ev | 154 | 112 | 98 | 120 | 61 | 99 | 65 | 28 | 3 | 1 |
| 10×10, 1000 ev | 996 | 642 | 608 | 370 | 307 | 616 | 381 | 154 | 25 | 7 |
| 200×1, 1000 ev | 1480 | 1033 | 966 | 547 | 492 | 882 | 863 | 333 | 53 | 12 |
| 3×50, 500 ev | 2223 | 1603 | 1579 | 657 | 567 | 807 | 231 | 90 | 25 | 6 |
| 20×20, 500 ev | 2011 | 1238 | 1159 | 687 | 583 | 1475 | 803 | 325 | 70 | 15 |

¹ `-XX:+UseSerialGC -Xmx128m`

### RL-shaped workload (8 sections, horizon 200)

| | DEVSpy | DEVSpy+mypyc | DEVSJAVA | DEVSJAVA tuned | xDEVS | PyPDEVS-min | adevs | Cadmium |
|---|---|---|---|---|---|---|---|---|
| ms/episode (steady) | 9.05 | 8.09 | 6.50 | 5.11 | 7.78 | 4.55 | 0.44 | 0.18 |
| 1st episode (cold) ms | 9.7 | 8.4 | 51 | 49 | 8.5 | 6.4 | 0.5 | 0.2 |
| 20 episodes, whole process ms | 224 | 201 | 387 | 344 | 224 | 113 | 11 | 6 |
| 64 sections, ms/episode | 212 | 212 | 229 | 179 | 66 | 32 | 15 | 2 |
| 16 workers: episodes/s | 1030 | 1133 | 444 | 540 | 1126 | 1926 | 18117 | 37154 |
| 16 workers: total RSS MiB | 223 | 226 | 6930 | 2298 | 380 | 186 | 60 | 60 |
| scaling 1→16 workers | 9.5× | 9.3× | 3.7× | 3.5× | 9.1× | 9.0× | 8.2× | 7.2× |

### What the numbers say

1. **The quick wins give 26–38%** (DEVStone), with no change in semantics.
2. **Against DEVSJAVA**, measured on its own terms:
   - Long, dense, steady-state runs: a warm, tuned JVM is still 1.8–2.8× faster.
   - Short runs, many episodes per process, and many parallel actors: DEVSpy
     wins. There is no JIT warm-up (first episode 9.7 against 49–51 ms), no JVM
     start (~100 ms), and 16 actors fit in 223 MiB against 2.3–6.9 GiB.
   - Parallel scaling: 16 DEVSpy processes give 9.5× the single-worker
     throughput, against 3.5–3.7× for 16 JVMs (each JVM brings its own JIT/GC
     threads and allocation pressure). A single multi-threaded JVM hosting all
     actors was not measured, and the DEVSJAVA facade is not designed for it.
   - Agent integration is not in these numbers. A Python agent (PyTorch, SB3)
     runs in-process with DEVSpy. With DEVSJAVA it needs a JVM bridge with one
     round-trip per decision, or a Java ML stack.
3. **The architecture, not Python, is the bottleneck.** PythonPDEVS-minimal is
   pure Python yet 3–18× faster than DEVSpy, and faster than DEVSJAVA on every
   DEVStone shape. It does three things DEVSpy does not:
   - It **flattens** the hierarchy at start-up (direct connection), so deep
     models cost the same as flat ones (3×50: 90 ms against 1603 ms).
   - It keeps an **event scheduler** (heap) of `time_next`, so a step only
     touches imminent and influenced models.
   - Its message routing is minimal: dicts of port → list, and no `Content` or
     `Port` objects per message.

   xDEVS-flat against xDEVS on 3×50 (231 against 807 ms) isolates the value of
   flattening alone.
4. **Compiling with mypyc gives little (0–12%) at this point.** The per-event
   work is still in interpreted code: user models, `Message`, `Content`,
   `Couprel` and `logging`, all in `devspy.modeling`. `my_model` must be
   annotated `Any` because a `Coordinator` passes a `Digraph`.

   What mypyc **costs**:
   - Simulator classes can't be monkeypatched or traced, so `trace_diff.py`
     needs `--model-level` and cProfile goes blind inside the engine.
   - `facade.deep_cloning()` (`copy.deepcopy`) **fails**, because native classes
     don't support the default reduce protocol. Making it work would need
     `__deepcopy__`/`__getstate__`.
   - Typing becomes stricter. Overrides must keep compatible signatures, so the
     DEVSJAVA-style `simulate(int)` → `simulate(float)` override had to be
     widened, and declared types are enforced at run time.
   - The package needs per-platform/per-Python wheels and a C toolchain to
     build from source.

   Recommendation: **don't ship mypyc now.** Reconsider it once the hot loop is
   self-contained (scheduler + flattened routing), when compiling would cover
   the whole per-event path.
5. **C++ engines are another league**: Cadmium is ~80–270× and adevs ~18–64×
   faster than DEVSpy, with ~4 MiB RSS. A Python engine can't get there.
   Bindings to a C++ kernel are the route if that is ever needed (the `devs` 0.1.8
   adevs wrapper from 2016 shows the idea; it was not tested).

### Semantic differences found between engines

- **PythonPDEVS** uses super-dense time `(t, age)`. When a transition happens
  at `(t, k)` and the previous transition was also at `t` (a zero-time
  cascade), the next event gets age `k+1` *even if it lands at a later real
  time*. Simultaneous arrivals at a later `t` can then be split across
  micro-steps into separate bags. In the RL model at t=19, two observations
  arrive in one bag and the third one micro-step later. DEVSpy, DEVSJAVA, xDEVS,
  adevs and Cadmium deliver one bag, the classic PDEVS behaviour. The
  trajectory changes slightly (17,723 decisions against 17,769 in 50
  episodes).
- **DEVSJAVA** keeps child simulators in a `HashSet` keyed by identity hash, so
  the order in which children are called, and the order of contents in a bag,
  can change between runs. DEVSpy uses lists and is deterministic. Both are
  valid PDEVS, because bags are unordered, but only DEVSpy gives reproducible
  traces.
- **Default `deltcon`** is `deltint(); deltext(e)` in DEVSpy and DEVSJAVA, but
  `deltint(); deltext(0)` in xDEVS, adevs, Cadmium and PythonPDEVS (Zeigler).

### Next performance steps (iteration 3+), in expected-gain order

1. **Flatten the hierarchy** when the simulator is built: precompute
   atomic-port → atomic-port routing, and keep `Digraph` only as a modelling
   construct. This targets the deep-model gap (3×50).
2. **Event scheduler** (heap or calendar of `t_n`, plus the set of models that
   received input) instead of scanning every simulator per step. This targets
   sparse models such as railway networks.
3. **Lighter message path**: no `Port` object per `Content`, no set copy in
   `Couprel.translate`, `__slots__`, and no `hasattr`/`isinstance` in the loop.
4. Re-evaluate mypyc, or Cython, once (1)–(3) make the loop self-contained.

## Iteration 2 backlog: features DEVSJAVA has and DEVSpy lacks

In order of relevance for this project:

1. **Variable structure**: adding or removing models and couplings at run time
   (`atomic.addModel/removeModel/addCoupling/removeCoupling`,
   `coordinator.setNewSimulator`, `updateChangedSimulators`). None of the
   RLDEVS4j projects use it.
2. **Real-time simulation** (`model.simulation.realTime`: `RTcoordinator`,
   `atomicRTSimulator`, `TunableCoordinator`): pacing to the wall clock, and
   input injection from threads.
3. **Activities** (`activity`, `holdIn(phase, sigma, activity)`): a threaded
   computation tied to a phase, whose result comes back as input.
4. GenCol collections (`Queue`, `Relation`, `Function`, `ZRelation`). Python's
   built-ins cover them, so this is low priority.
5. Distributed simulation (`model.simulation.distributed`). Declared out of
   scope.
