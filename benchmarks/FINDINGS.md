# Findings log

Raw data: `results/*.jsonl`. Tables: `results/SUMMARY.md`. Everything below was
measured on an AMD Ryzen 7 5700X (8C/16T), Linux 6.8, CPython 3.12.3, OpenJDK 17,
using DEVSJAVA = Devs-Suite-Facade `d8c4917` ("CACIC 2022 version").

## Iteration 1 — quick wins (branch `perf/quick-wins`)

### Baseline profile (DEVSpy `0857ff6`, DEVStone 20×20)

| Hotspot | Share of runtime |
|---|---|
| `Coordinator.next_tn` re-computing `min` recursively over the whole tree every step | ~20% |
| `Atomic.show_state` building two f-strings and calling `logging` per transition, with logging disabled | ~12% |
| Coordinator loops calling `compute_input_output` / `delt_func` on every child, imminent or not | most of the rest of the per-step overhead |

DEVSJAVA has the same O(N)-per-step structure. Its coordinator is worse in
principle: it reaches every child via reflection (`ensembleBag.tellAll` →
`holder`) and builds a `TreeSet` of all children's `tN` per step. The JIT hides
much of that cost.

### Changes

1. `util.logging.is_enabled(level)`. `Atomic.show_state` and the `ITERATION ...`
   log calls return early when the level is disabled. Simulators call
   `show_state` only when the model overrides it (`custom_show_state`) or
   logging is on, so user-defined `show_state` keeps running as before.
2. `Coordinator.next_tn` = `min(child.t_n)` without recursion. The invariant
   that each child's `t_n` is current after `initialize`/`wrap_deltfunc` already
   held.
3. `Coordinator.compute_input_output` runs λ only on imminent children
   (`t_n == t`). `Coordinator.wrap_deltfunc` runs δ only on children that are
   imminent or have a non-empty input bag.

### Formal validation (Parallel DEVS abstract simulator, Chow & Zeigler 1994)

- (2) The coupled model's time of next event is defined as `tN = min_{d∈D} tN_d`.
  This is unchanged; only the way it is computed changed.
- (3a) The PDEVS coordinator sends the `@`-message (compute output) only to
  `IMM(t) = {d | tN_d = t}`. Non-imminent components have no output at `t` by
  definition. Previously they were called and returned an empty bag, so skipping
  them is the textbook behaviour.
- (3b) The `*`-message (state transition) goes to `IMM(t) ∪ INF(t)`, the
  imminents plus the components receiving input. Any other component keeps `s`
  and `tL`, so its elapsed time keeps accumulating. The old atomic-level
  `wrap_deltfunc` already returned early for these, so δ is never applied to
  them. For nested coordinators the old code also set `tL := t` on a no-op
  round. That value is never read (only top-level `sim_inject` uses `tL`), and
  the new behaviour (untouched `tL`) is the one the abstract simulator
  prescribes.
- (1) No semantic content; only logging I/O.

Empirical confirmation: `trace_diff.py` records every λ and δ (time, model,
int/ext/con, `e`, input/output bags) for the 3 examples, 3 DEVStone shapes and
200 random hierarchical models (depth ≤ 4, ties, `ta = 0`, confluent events). The
total is ~30k events, including 2,959 confluent transitions and 143 models with
simultaneous external events at `e = 0`. The traces of `0857ff6` and of the
quick-wins tree are **byte-identical** (`ALL 2acb222159b348e8`).

Downstream, RLDEVSpy-TrackRailway gives 106 passed and 4 failed both before and
after the change. The 4 failures in `tests/env/test_invariants.py` predate this
work.

### Results

DEVStone-like model, simulation only, ms (warm median):

| config | DEVSpy base | DEVSpy quick-wins | Δ | DEVSJAVA default | DEVSJAVA SerialGC+Xmx128m |
|---|---|---|---|---|---|
| 5×3, 1000 ev | 153 | 112 | −27% | 121 | 68 |
| 10×10, 1000 ev | 935 | 657 | −30% | 365 | 289 |
| 200×1, 1000 ev | 1488 | 1037 | −30% | 565 | 486 |
| 3×50, 500 ev | 2198 | 1508 | −31% | 651 | 564 |
| 20×20, 500 ev | 2007 | 1272 | −37% | 667 | 581 |

- In a long, dense, steady-state run, warm and tuned DEVSJAVA is still 1.65–2.7×
  faster. The worst case is the deep hierarchy (3×50): each message is
  re-translated and a new `Content` is created at every level.
- End-to-end process time (startup + build + run): DEVSpy wins short and medium
  runs. For 10×10 with 1000 events, DEVSpy takes 683 ms against 720 ms for
  default DEVSJAVA (519 ms tuned). Peak RSS is **14 MiB** against 415 MiB
  (default) or 153 MiB (tuned).

RL-shaped workload (8 sections, horizon 200, `reset()` per episode; decisions
and reward identical across engines):

| | DEVSpy | DEVSJAVA default | DEVSJAVA tuned |
|---|---|---|---|
| ms/episode, steady state | 9.1 | 6.4 | 5.2 |
| first episode (cold) | 9.8 | 50 | 47 |
| 20 episodes, whole process | **220 ms** | 383 ms | 309 ms |
| 16 parallel workers, episodes/s | **1108** | 485 | 574 |
| 16 parallel workers, total RSS | **224 MiB** | 6.7 GiB | 2.3 GiB |
| 64 sections, ms/episode | 210 | 220 | 173 |

- DEVSpy has no warm-up, so it wins every regime where per-process cost
  dominates: short experiments, hyper-parameter sweeps, and many actors.
- Parallel scaling from 1 to 16 workers is 10.4× for DEVSpy against 3.8× for the
  tuned JVM. Each JVM brings its own JIT and GC threads and allocates heavily
  (reflection, boxing), so 16 JVMs saturate the 8 physical cores and memory
  bandwidth. Caveat: a single multi-threaded JVM hosting 16 actors was not
  measured, and DEVSJAVA's facade is not designed for that.
- Agent integration is not in these numbers. A Python agent (PyTorch, SB3) runs
  in-process with DEVSpy. With DEVSJAVA it needs a JVM bridge (Py4J/JPype) with
  one round-trip per decision, or a Java ML stack.

### Not done in this iteration (blocked or pending)

- **Other Python engines** (xDEVS.py 3.0.0 from PyPI, PythonPDEVS from
  github.com/capocchi/PythonPDEVS, `devs` 0.1.8 = adevs wrapper) and **C++
  engines** (adevs, Cadmium v2). The sources were cloned, but installing or
  building third-party code was blocked by the session's permission policy and
  needs explicit approval. The official PythonPDEVS server
  (msdl.uantwerpen.be) refused connections.
- **mypyc build of `devspy.simulation`**: needs `mypy` from PyPI (same block).
- Published reference for context: the DEVStone metric papers
  ([arXiv 2309.16544](https://arxiv.org/abs/2309.16544),
  [arXiv 2402.05483](https://arxiv.org/abs/2402.05483)) report adevs and xDEVS
  C++ as the fastest engines, and PyPDEVS-minimal under PyPy at ~4× PyPDEVS full.

### Next performance steps (measured hotspots, in expected-gain order)

1. Per-coordinator event heap (imminent set), so per-step cost is O(k log N)
   instead of O(N). This is where sparse models (many idle components, as in
   railway networks) can beat DEVSJAVA outright.
2. Flatten the hierarchy at build time (direct atomic→atomic coupling tables).
   This targets the 3×50 case.
3. Message path: `Content` builds a `Port` per message, `Couprel.translate`
   copies a set, `__slots__` are missing in `Content`/`Port`/`Pair`, and the
   hot loop uses `hasattr`/`isinstance`.
4. Compiled core (mypyc/Cython) once the above is done.

## Iteration 2 backlog — features DEVSJAVA has and DEVSpy lacks

In order of relevance for this project:

1. **Variable structure**: add or remove models and couplings at run time
   (`atomic.addModel/removeModel/addCoupling/removeCoupling`,
   `coordinator.setNewSimulator`, `updateChangedSimulators`). None of the
   RLDEVS4j projects use it.
2. **Real-time simulation** (`model.simulation.realTime`: `RTcoordinator`,
   `atomicRTSimulator`, `TunableCoordinator`): paced to the wall clock, with
   threaded input injection.
3. **Activities** (`activity`, `holdIn(phase, sigma, activity)`): a threaded
   computation bound to a phase whose result comes back as an input.
4. GenCol collections (`Queue`, `Relation`, `Function`, `ZRelation`): Python's
   built-in types cover these, so this is low priority.
5. Distributed simulation (`model.simulation.distributed`): declared out of
   scope.
