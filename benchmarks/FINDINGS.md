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

## Iteration 3: flat event-driven kernel (branch `perf/flat-kernel`)

We dropped the goal of mirroring DEVSJAVA's tree of nested coordinators. The
profile after the quick wins showed that ~70% of the time on the 3×50 model went
into re-routing each message at every level: `send_messages` +
`Couprel.translate` + new `Content`/`Port`/`Pair` objects per hop. Delivering
10,000 messages to the sink created 315,000 `Content` objects.

### Design

1. **Flattening at construction.** The coordinator walks the `Digraph` tree
   once. It creates one `CoupledSimulator` per atomic, in depth-first component
   order, and resolves every coupling path (EIC/IC/EOC through any number of
   levels) into `fanout`: output port → `[(dst_port, [target sims])]`.
   `Digraph` is now only a modelling construct.
2. **Event heap** of `(t_n, index, version)` with lazy invalidation. Each round
   pops IMM(t), applies λ, routes the outputs, applies δ to IMM(t) ∪ INF(t)
   sorted by index, and pushes only those back.
3. **Light messages.** There is one `Content` per destination port, shared by
   all its receivers, or the source `Content` itself when the port name
   matches. `Content` stores the port name and builds a `Port` only on demand.
4. **Single loop**, with no per-level hooks or `hasattr` in the hot path.
5. `reset()` re-initializes the atomics (only atomics, in component order, as
   RLDEVSpy-TrackRailway expects) and rebuilds the heap, **without
   re-flattening**.

### Formal validation

- **Flattening** is the *direct connection* construction that PythonPDEVS also
  uses. It is justified by PDEVS closure under coupling (Zeigler, Praehofer &
  Kim): a hierarchical PDEVS model and the flat
  model whose couplings are the composition of the path couplings have the same
  I/O behaviour. Couplings carry no transfer functions in DEVSpy, so
  composition is just concatenating the paths. A digraph input coupled straight
  to its own output is not a valid DEVS coupling (d ≠ N). The hierarchical
  kernel silently dropped it, and so does the flat one.
- **Scheduler**: the round still applies λ to IMM(t) and δ to IMM(t) ∪ INF(t),
  and `tN = min tN_d` (the heap minimum). Only the data structure changed.
- **Determinism**: λ and δ run in depth-first index order, the same order the
  hierarchical kernel used. The order of contents inside a bag can differ when
  messages reach a receiver from different hierarchy levels. Bags are
  multisets in PDEVS, so this is semantically irrelevant.

### Empirical validation

- `trace_diff.py --model-level` now also records the absolute time of external
  transitions. Over 206 models it captures 48,617 events with time, `e` and
  bags, plus the multiset of root outputs. The result is **identical** for the
  baseline (`0857ff6`), quick-wins (`eb23a82`) and flat (`6aa16ed`) kernels:
  `ALL aa4c587580984747`.
- `tests/test_flat_kernel.py` covers routing across 3 levels up and 3 levels
  down, `sim_inject` into a nested atomic, repeated `reset()`, incremental
  `simulate_to_time` against a one-shot run, `deep_cloning`, and the dropped
  input-to-output coupling. These tests pass on **both** the hierarchical and
  the flat kernel.
- RLDEVSpy: 231 passed. RLDEVSpy-TrackRailway: unchanged (106 passed, 4
  failures that predate this work).

### Results

DEVStone-like, simulation ms (warm median):

| config | DEVSpy base | quick wins | **flat** | PyPDEVS-min | DEVSJAVA tuned | xDEVS flat |
|---|---|---|---|---|---|---|
| 5×3, 1000 ev | 154 | 112 | **38** | 28 | 61 | 65 |
| 10×10, 1000 ev | 996 | 642 | **248** | 154 | 307 | 381 |
| 200×1, 1000 ev | 1480 | 1033 | **532** | 333 | 492 | 863 |
| 3×50, 500 ev | 2223 | 1603 | **145** | 90 | 567 | 231 |
| 20×20, 500 ev | 2011 | 1238 | **515** | 325 | 583 | 803 |

RL-shaped workload:

| | quick wins | **flat** | PyPDEVS-min | DEVSJAVA tuned | xDEVS |
|---|---|---|---|---|---|
| ms/episode, 8 sections | 9.05 | **5.21** | 4.55 | 5.11 | 7.78 |
| ms/episode, 64 sections | 212 | **60.7** | 31.7 | 179 | 65.9 |
| 20 episodes, whole process ms | 224 | **143** | 113 | 344 | 224 |
| 16 workers, episodes/s | 1030 | **1682** | 1926 | 540 | 1126 |
| 16 workers, total RSS MiB | 223 | **221** | 186 | 2298 | 380 |

Takeaways:

- **2.6–11× faster than quick wins and 2.8–15× faster than the baseline.** The
  deep 3×50 hierarchy gains the most (2223 → 145 ms): depth no longer costs
  anything at run time.
- **DEVSJAVA is matched or beaten.** DEVSpy is faster than a tuned, warm JVM on
  4 of 5 DEVStone shapes, and 8% slower on the flat 200×1 shape. On RL it ties
  per episode with 8 sections and is 2.9× faster with 64 sections. It keeps the
  advantages already measured: no warm-up, ~10× less RAM, and 3.1× the
  throughput with 16 actors.
- **PyPDEVS-minimal is now 1.4–1.6× ahead on DEVStone** (it was 3–18× ahead)
  and 1.15–1.9× ahead on RL. DEVSpy is faster than xDEVS (with or without
  flattening) everywhere.
- **Where the remaining gap is.** In the flat kernel's profile (20×20), the
  kernel is ~32% of the time. The rest is the model and the DEVSJAVA-style
  modelling API: `IntEnt` wrappers, iterating `Message`/`Content`, and the
  `passivate → passivate_in → hold_in` chain. The PyPDEVS port uses plain ints
  and dicts. Closing the gap further is mostly about a leaner modelling API,
  such as plain values on ports and direct state assignment, not about the
  kernel.

## Iteration 4: plain dict bags, no wrappers (branch `perf/dict-messages`, 0.2.0)

This is a **breaking change**, decided as a clean break: `Message`, `Content`,
`Port`, `Entity`, `IntEnt`, `DoubleEnt` and `Pair` were removed. A bag is now a
plain `dict[str, list]` (port → values), exported as the type alias
`devspy.Bag`. Values are plain Python objects. `Couprel` stores
`(component, port)` tuples.

```python
def deltext(self, e, x):  for job in x.get("in", ()): ...
def out(self):            return {"out": [self.job]}       # {} = no output
```

Kernel changes made at the same time:

- Routing appends values straight into the receiver's dict. Each receiver gets
  its own list per port, so senders may reuse their lists and receivers may
  mutate theirs.
- The `simulate` loops call a single fused `_round(t)`: pop IMM, λ, then δ.
- The sort key is C-level (`attrgetter("index")`).
- `sigma` is read directly when the model doesn't override `ta()`.
- `__slots__` on the simulators.
- `passivate()`/`passivate_in()` assign fields directly instead of going
  through `hold_in()`.

### Validation

- `trace_diff.py --model-level` gives the same `ALL aa4c587580984747` (48,617
  events). The trace tool and its models were ported to the new API. With plain
  ints, `repr(5)` renders exactly like the old `IntEnt(5)`, so the digests are
  directly comparable.
- Example outputs (`gpt_model`, `mm1_queue`, `manufacturing_line`) are
  byte-identical to the previous branch. Benchmark counters are unchanged.
- **Downstream migration.** RLDEVSpy (4 modules plus tests) is at 231/231.
  RLDEVSpy-TrackRailway (3 modules) is unchanged at 106 passed and 4 failures
  that predate this work.
- **End-to-end trajectory check**, `downstream/trackrailway_trace.py`: real
  TrackRailway episodes (1/3/5 trains × 3 seeds × 3 episodes with `reset()`, a
  seeded random agent, and per decision an observation hash, the action and the
  reward). The old stack (flat kernel + RLDEVSpy/TrackRailway `main`) and the
  new stack give **identical** results: `ALL 11cc8d93d6e2c704`.

### Results

DEVStone-like, simulation ms (warm median):

| config | baseline | flat kernel | **dict bags** | PyPDEVS-min | DEVSJAVA tuned | Cadmium (C++) |
|---|---|---|---|---|---|---|
| 5×3, 1000 ev | 154 | 38 | **23** | 28 | 61 | 1 |
| 10×10, 1000 ev | 996 | 248 | **147** | 154 | 307 | 7 |
| 200×1, 1000 ev | 1480 | 532 | **322** | 333 | 492 | 12 |
| 3×50, 500 ev | 2223 | 145 | **86** | 90 | 567 | 6 |
| 20×20, 500 ev | 2011 | 515 | **310** | 325 | 583 | 15 |

RL-shaped workload:

| | flat kernel | **dict bags** | PyPDEVS-min | DEVSJAVA tuned |
|---|---|---|---|---|
| ms/episode, 8 sections | 5.21 | **3.16** | 4.55 | 5.11 |
| ms/episode, 64 sections | 60.7 | **26.5** | 31.7 | 179 |
| 16 workers, episodes/s | 1682 | **3100** | 1926 | 540 |
| 16 workers, total RSS MiB | 221 | **206** | 186 | 2298 |
| whole process, 10×10 DEVStone ms | 286 | **181** | 179 | 557 |

Real application (RLDEVSpy-TrackRailway, `downstream/trackrailway_bench.py`,
random agent, 7200 s episodes, `results/trackrailway.jsonl`):

| ms/episode | original (`0857ff6`) | flat kernel | **dict bags** |
|---|---|---|---|
| 1 train | 175 | 66 | **50** (3.5×) |
| 5 trains | 333 | 141 | **109** (3.0×) |

- DEVSpy is now **faster than PyPDEVS-minimal on every DEVStone shape and every
  RL measure**, and 1.5–6.6× faster than a tuned, warm DEVSJAVA on DEVStone.
- Since the start of this work: 4.6–26× on DEVStone and 3–3.5× on the real
  TrackRailway environment.

### What else could be optimized (measured or analysed)

| Lever | Effect | Verdict |
|---|---|---|
| mypyc on the current kernel | 7–22% faster (best in RL: 3.18 → 2.48 ms/ep) | It still breaks `deep_cloning()` (the snapshot test fails), blinds profiling, and needs per-platform wheels. Worth it only as an *optional* compiled build with a pure-Python fallback, after adding `__deepcopy__` support. |
| Disabling the GC during runs | 0–5%, within noise for RL | Not worth it. A library shouldn't touch the global GC. |
| Inlining `_lambda`/`_delta` into `_round` | ~2–4% estimated (two calls per round) | Low priority. It would cost readability. |
| Scheduler for dense models (array scan instead of heap) | Heap operations are ~10–13% on dense DEVStone | A sparse workload loses if we switch. Revisit only with an adaptive scheduler, as PyPDEVS does. |
| PyPy | Not measured (not installed). DEVSpy is now pure Python with no dependencies, so it should be PyPy-friendly. | Measure next. It could be the largest remaining win, but RLDEVSpy's PyTorch/NumPy stack is CPython-only. |
| CPython 3.13+ | Not measured (only 3.10/3.12 installed) | Free upgrade for users. |
| **TrackRailway modelling** | Kernel ≈ 34% of a real episode. TrackRailway models ≈ 48%. Each train emits an event on every movement tick (~15.6k events/episode), and the observer processes every one. | The biggest remaining win is in the model, not the engine: emit only on section changes or arrivals and compute positions analytically. This change belongs in TrackRailway. |
| `phase_is()` | 2.1M calls (4.6%) in TrackRailway | Use `self.phase == "x"` in hot model code. |

## Iteration 5: robustness and PDEVS defaults (branch `feat/robustness`, 0.3.0)

No performance goal. The aim is to fail loudly on invalid models and to drop
the DEVSJAVA parity quirks, which the project no longer needs to mirror. All of
it is breaking (see `CHANGELOG.md`), hence 0.3.0.

| Change | Before | After |
|---|---|---|
| Network validation in `_flatten` | Couplings to unknown names or undeclared ports were dropped or routed anyway; `in -> out` was dropped silently; duplicate names made routing ambiguous | `ModelStructureError` |
| Zero-time loop | A `ta() == 0` feedback loop hung the process | `ZeroTimeLoopError` after `max_rounds_per_instant` (100 000) rounds at one time |
| Run without `initialize()` | `DevsSuiteFacade(digraph).simulate_to_time(t)` silently did nothing (empty heap) | The loop initializes first |
| `TimeAtomicSimulator.simulate(t)` | Compared the iteration counter with `t` | Runs events with `t_n <= t` |
| Default `deltcon` | `deltint(); deltext(e, x)` with the pre-`deltint` `e` | `deltint(); deltext(0, x)` |
| `sim_inject` out of range or on an undeclared port | Dropped silently (or logged) | `ValueError` |

### Formal argument

- **Validation** only rejects networks that are not coupled DEVS models. In
  the coupled-model definition (Zeigler, Praehofer & Kim 2000; Chow 1996),
  EIC ⊆ X_N × ∪X_d, EOC ⊆ ∪Y_d × Y_N and IC ⊆ ∪Y_a × ∪X_b with a ≠ b, all
  between the declared port sets. Self-influence is excluded (i ∉ I_i). The
  check is applied to the *flattened* network, so a digraph-level coupling
  `d -> d` is accepted when it only connects distinct atomics inside `d`, which
  is what closure under coupling gives. Valid networks are flattened exactly as
  before.
- **The zero-time guard** concerns legitimacy: a DEVS model is legitimate iff
  every finite interval contains finitely many transitions. More than N
  rounds at one instant is a cheap witness that a model is probably
  illegitimate. A legitimate model with at most N simultaneous rounds runs
  unchanged. The bound is configurable.
- **Injection bounds** are the abstract simulator's own synchronization check:
  an external event at t requires t_l ≤ t ≤ t_n (Zeigler's simulator reports
  a "bad synchronization" error otherwise).
- **Default `deltcon`**: Chow & Zeigler's PDEVS default is
  δcon(s, x) = δext(δint(s), 0, x). After δint the model is in a new state
  entered at t, so the elapsed time in it is 0. Passing the old `e` made a
  `cont(e)` subtract time already consumed by the internal transition.
- **Time-gated atomic runs and lazy initialization** follow the abstract
  simulator's root loop (`initialize`, then rounds while t_n ≤ t_end).

### Validation

- `trace_diff.py --model-level`: of the 206 cases (48,617 events), only
  `gpt` changes, and within it exactly one event:
  `20 generator ext e=2 x=[stop=1]` → `18 generator ext e=0 x=[stop=1]`. This
  is the generator's confluent transition at t=20 (its own event plus the
  transducer's `stop`) through the default `deltcon`. The tool prints
  `t_l + e`, which is why the time column also moves. The generator ignores
  `e`, so the outputs and later transitions are identical. All other cases,
  including the 200 random hierarchical models with ties and zero-time
  advances, hash the same. New `ALL 3e6ae84e413300cc`, which is the expected
  change.
- Example outputs (`gpt_model`, `mm1_queue`, `manufacturing_line`) are
  byte-identical. The only example change is that the GPT generator now
  declares its `stop` input port, which validation required.
- **Downstream:** RLDEVSpy has 231/231 passing, with no source changes needed.
  TrackRailway is still at 106 passed with the same 4 pre-existing failures. The
  end-to-end trajectory digest is unchanged, `ALL 11cc8d93d6e2c704`.
- New `tests/test_robustness.py` (15 tests) covers each rule.

> **Correction (iteration 13):** the before/after numbers in this paragraph were invalid, because both sides ran the same code. Corrected numbers are in iteration 13.

### Cost

The guard adds one float comparison per round in `_run`. Measured against
`23c78d0` (`results/devstone.jsonl` with tag `it5-robustness`, and
`results/rl.jsonl`), the difference is within noise: DEVStone 20×20 311.8 →
314.9 ms, 3×50 85.7 → 86.4 ms; RL m=8 3.24 → 3.22–3.32 ms/ep; m=64
27.1 → 26.6–26.8 ms/ep; P=16 2869 → 2861 eps/s. Decisions and rewards are
identical.

## Iteration 6: reference abstract simulator as a permanent oracle (branch `test/reference-simulator`)

Until now every engine change was validated with a manual trace diff between
two versions of DEVSpy. That shows a change preserves behaviour, not that the
behaviour is PDEVS. `tests/reference_pdevs.py` is an independent, literal
implementation of Chow & Zeigler's hierarchical abstract simulator: one
coordinator per digraph, no flattening, no heap, couplings translated level by
level at every round. `tests/test_reference_pdevs.py` runs both engines on
random hierarchical models with these properties:

- Depth up to 3, with 1–2 input and output ports per atomic.
- Fan-in and fan-out through EIC, IC and EOC.
- Delays in {0, 0.5, 1, 2, 3}, which produce ties and zero-time advances.
- Half the atomics override `deltcon` and half use the default; half use `cont(e)`.

The suite runs 300 models without input and 150 with random external
injections. The injections fall on a 0.25 grid, so many coincide with internal
events.

Over the 300 models without input there are 28,526 transitions:

| Measure | Count |
|---|---|
| External transitions | 14,415 |
| Internal transitions | 12,695 |
| Custom confluent transitions | 1,416 |
| Transitions with `e = 0` | 4,427 |
| Multi-value bags | 2,365 |
| Root outputs | 3,342 |

Each atomic logs its own view of every transition (clock, kind, e, and the
input bag as a multiset), and the comparison is per model. That is exactly what
PDEVS determines: simultaneous transitions of different models commute, and a
bag has no order. The whole suite takes about one second.

**Is the oracle sensitive?** `benchmarks/mutation_check.py` injects known kernel
bugs one at a time, and **all 9 are caught**:

- confluent dispatched as `deltext`;
- the old default-`deltcon` `e`;
- receivers left without δ;
- stale heap entries used;
- `e` measured from `t_n`;
- only the first value per port delivered;
- a wrong `ta()` on one model;
- an injection without λ;
- root output dropped.

The oracle itself is also checked against the hand-derived GPT trace.

**Bug found.** `sim_inject` at exactly `t_n` applied δ to the imminent models
without running their λ first: an (x, t) at t = tN with no preceding (*, t), so
their outputs at that instant were lost. On 0.3.0 as published in #6, 50 of the
150 injection cases fail. The fix:

- `Coordinator.wrap_deltfunc` now runs λ and routing first whenever it is not
  preceded by `compute_input_output(t)`.
- `AtomicSimulator.sim_inject` does the same.
- The root outputs of the injected round are shown after the round, as in `_run`.

Neither TrackRailway nor RLDEVSpy injects, and `trace_diff.py --model-level`
is unchanged (`ALL 3e6ae84e413300cc`).

## Iteration 7: heap hygiene (branch `perf/heap-hygiene`)

Three cheap kernel levers from the "what else" list (A4, A5, A7), now guarded by
the oracle.

> **Correction (iteration 13):** the DEVStone/RL "no change" results below came from an invalid comparison, because both sides ran the same code. Measured correctly, this iteration makes RL **14–17% faster** and DEVStone 2–3% slower. A7 was re-measured correctly and is still within noise. See iteration 13. The watchdog and TrackRailway numbers were valid.

| Lever | Change | Result | Kept? |
|---|---|---|---|
| A4: heap compaction | Rebuild the heap (`heapify` of the live `(t_n, index, version)`) when it grows past `2·n + 64` entries | DEVStone, RL and TrackRailway: no change (their heaps never fill with stale entries; TrackRailway peaks at 28). **Watchdog pattern: 28–34% faster, heap bounded, RSS 144 → 41 MiB** | Yes |
| A5: skip unchanged reschedules | A receiver whose new `t_n` equals its old one keeps its heap entry: no version bump, no push | No change on the benchmarks. It saves a push and a stale entry for the classic busy server that does `cont(e)` on input | Yes (3 lines) |
| A7: root routes split out of the λ inner loop | Separate `root_fanout` per simulator | Within ±1% on DEVStone and RL | **No, reverted** |

**Watchdog benchmark** (`benchmarks/timeout_model.py`, `results/timeout.jsonl`).
A broadcaster pings N watchdogs every 0.01, and each ping restarts the
watchdog's timeout. Every restart leaves a stale entry behind, and stale entries
only drain once simulated time passes them, so without compaction the heap
holds about N·timeout/period entries.

| N, timeout, end | before: wall, heap, RSS | after: wall, heap, RSS |
|---|---|---|
| 1000, 10, 20 | 2360 ms, 999,001, 144 MiB | 1548 ms, 2,001, 41 MiB |
| 200, 50, 60 | 1058 ms, 1,000,001, 143 MiB | 771 ms, 201, 41 MiB |
| 1000, 1, 20 | 2303 ms, 99,001, 41 MiB | 1536 ms, 2,001, 41 MiB |

**PDEVS argument.** Both changes preserve the scheduler invariant: every
simulator with t_n < ∞ has exactly one heap entry carrying its current version,
and next_tn = min over those entries. A5 keeps a still-correct entry instead of
replacing it with an identical one. A4 discards only entries whose version is
stale, which `_pop`/`next_tn` would skip anyway. Which models are imminent, and
when, does not change.

**Validation.**

- The oracle has a new variant with `_heap_limit = 0`, which rebuilds the heap
  after every round (100 models). Without it the small random models never
  trigger a rebuild, and a broken rebuild went unnoticed. `mutation_check.py`
  now has 11 mutations, two of them aimed at these changes, and **all are caught**.
- `trace_diff.py --model-level` is unchanged (`ALL 3e6ae84e413300cc`), and so
  is the TrackRailway trajectory digest (`ALL 11cc8d93d6e2c704`).

## Iteration 8: driving, observing and checkpointing a simulation (branch `feat/step-api`)

API work (C1–C3), no performance goal.

| API | What | Why |
|---|---|---|
| `advance(until, stop_on_output)` | Runs rounds and returns the root outputs as `(t, bag)` | Root outputs used to be printable only |
| `inject(bag, at=None)` | Runs the rounds strictly before `at`, then delivers (x, at) | Gym-style control from outside the model, without computing `e` |
| `Observer` | `on_output(t, model, y)` and `on_transition(t, model, kind, e, x)` | Traces, metrics and animation without monkeypatching |
| `snapshot()` / `restore()` | Copies the model attributes, times and heap; restores in place | Checkpoints and rollouts. `deep_cloning()` makes new model objects, so the user's references go stale |

**PDEVS argument.**

- `advance` is the root coordinator loop: it sends (*, t) and then (x = ∅, t)
  while t_N ≤ until.
- `inject(at=t)` first completes every round with t_N < t, using the bound
  `math.nextafter(t, -inf)`. It then sends (x, t). If t = t_N, that is preceded
  by (*, t), which is the confluent case fixed in iteration 6.
- The absolute-time `inject_at` avoids `t_l + (t - t_l) ≠ t` rounding. With
  that rounding a confluent injection could silently become two rounds.
- Observers are notified after the fact and cannot change routing.
- `restore` resets the full simulator state: every model's attributes, `t_l`,
  `t_n`, `version`, the pending input bags and the heap. The scheduler
  invariant therefore holds again.

**Validation** (oracle from iteration 6):

- `test_step_api_matches_reference` (150 models): the injection oracle driven
  only through `inject`/`advance`. Per-model transitions and root outputs with
  their times match.
- `test_snapshot_restore_replays_the_reference` (100 models): advance to 13.3,
  snapshot, then three times over restore and run to 40. Each replay matches
  the reference.
- `test_observer_sees_every_transition_without_perturbing` (100 models): logs
  with an observer attached equal the reference, and the observer's
  (t, kind) sequence per model equals the model's own log. A default
  `deltcon` counts as one `"con"`.
- 11 unit tests in `tests/test_step_api.py`.
- The mutation check still catches all 11 mutations.

> **Correction (iteration 13):** the before/after numbers in this paragraph were invalid, because both sides ran the same code. Corrected numbers are in iteration 13.

**Cost** with no observer attached is one emptiness check per output and per
transition. Against `22780c0` the difference is within noise: DEVStone 20×20
328.5 → 333.2 ms on one sample, other shapes ±1%; RL m=64 22.74/23.14 →
22.76/23.17 ms/ep across repeated runs.

## Iteration 9: variable structure (branch `feat/variable-structure`)

Backlog item 1: DEVSJAVA's `addModel`, `removeModel`, `addCoupling` and
`removeCoupling`.

- **API**: the `Digraph` mutators, plus the `Atomic` shortcuts (`add_model`,
  `remove_model`, `add_coupling`, `remove_coupling`) on the parent digraph.
  They work from outside between runs and from inside transitions.
- **Kernel**: a mutated digraph calls `coordinator.structure_changed()`. Inside
  a run or a δ phase the change is deferred, and `_restructure()` runs after
  the round. That method:
  - re-flattens, reusing the existing `CoupledSimulator` objects, which keep
    their `t_l`, `t_n`, version and state;
  - initializes new atomics at `t_l`;
  - drops removed atomics and rebuilds the heap;
  - rolls back if the new network is invalid.

  An invalid change made outside a round is also undone in the digraph.
  DEVSJAVA does the same deferral: it collects the simulators in
  `newSimulators` and `deletedSimulators` and applies them in
  `updateChangedSimulators()` after the δ phase.

**PDEVS argument.** In DSDEVS (Barros 1995, 1997) the network executive's
transition at t defines the structure that holds from t on. The δ functions of
round t are computed with the structure in force when that round began.
Deferring the change to the end of the round gives exactly that. Every model
of round t sees the same couplings, and outputs of t are routed by the old
structure.

- A component added at t starts in its initial state with t_l = t.
- A removed component leaves both the schedule and the network.

Barros showed DSDEVS is closed under coupling, so the flat equivalent is a
valid (DS)DEVS network. Applying the change mid-round would make a model's
input depend on the δ order of its siblings. The mutation check confirms that
the oracle rejects that variant.

**Validation.**

- The oracle supports dynamic structure literally: after each round every
  reference coordinator re-reads its digraph and initializes new components
  at t.
- `test_variable_structure_matches_reference` covers 200 random models with
  "spawners". These atomics, on internal transitions, add coupled siblings or
  remove one, and also receive random injections. In total there were 676
  additions and 448 removals.
- 8 unit tests in `tests/test_variable_structure.py`.
- `mutation_check.py` gains 4 structure mutations, for 15 in total, and **all
  are caught**:
  - change applied mid-round;
  - new atomics scheduled from t=0;
  - re-flatten losing state;
  - removal keeping couplings.
- `trace_diff.py --model-level`, the TrackRailway trajectories, RLDEVSpy and
  TrackRailway tests are all unchanged.

> **Correction (iteration 13):** the before/after numbers in this paragraph were invalid, because both sides ran the same code. Corrected numbers are in iteration 13.

**Cost**: one attribute check per round. Against `faab105` the difference is
within noise on DEVStone (±1.5%) and RL.

## Iteration 10: real time and activities (branch `feat/real-time`)

Backlog items 2 and 3: DEVSJAVA's `RTcoordinator`/`TunableCoordinator` and
`activity`.

- **`RealTimeRunner`** (`facade.real_time(speed, clock)`) runs the coordinator
  one round at a time (`_run(1, t_next)`). Simulated time t is reached at wall
  time `start + (t - t0)/speed`. Other threads only touch a `queue.Queue`
  inbox, through `post(...)`, `post(..., to=atomic)` and `stop()`.
  - An input is delivered at the simulated time that matches its arrival,
    clamped to [t_l, t_n].
  - Every due event runs first. When the host falls behind, overdue events run
    back to back.
- **Activities.** `Atomic.start_activity(fn, *args, port=...)` runs `fn` in a
  thread, and its result comes back as external input on the model's port
  (`inject_to`). An exception stops the run, and `cancel()` drops the result.
  DEVSJAVA's logical-time activities draw a random completion time and mutate
  `sigma`, which is not deterministic. In DEVSpy activities are real-time only;
  in logical time a known duration is just `hold_in`.

**PDEVS argument.** Real time does not change the abstract simulator, only
when its rounds run on the wall clock.

- External input is an (x, t) message at a t with t_l ≤ t ≤ t_N, as the
  synchronization check requires.
- An activity result on an atomic's port is equivalent to an external input on
  a hidden root input port coupled to that port.
- One choice is forced: a runner cannot know an input will arrive at exactly
  an internal event's time, so such an input goes in its own round after the
  event, at the same t. That is a legal PDEVS trajectory, with the input
  arriving an infinitesimal later. It differs only in that the input is not
  confluent with the event.

**Validation.**

- The oracle gains `confluent_injections=False`, which encodes that policy.
- `test_real_time_run_matches_reference` covers 100 random models with posts
  scheduled on a virtual clock at speed 2. Per-model transitions and root
  outputs match.
- Unit tests check:
  - wall-time pacing at speeds 0.5, 1 and 2;
  - posted inputs arriving at the matching t;
  - an input arriving with a due event;
  - catching up after host stalls;
  - `stop()`.
- With real threads and the real clock: a post from another thread, an
  activity result arriving ≥10 ms later, an activity exception propagating,
  and activities refused outside real time. The threaded tests passed 30/30
  repeated runs.
- `mutation_check.py`: 17 mutations, all caught, including "input delivered at
  the last event" and "pacing ignores speed".
- The kernel hot path is unchanged.

## Iteration 11: exact time and API cleanup (branch `feat/api-cleanup`)

- **B5, exact time.** Simulation time started at `0.0`, so `0.0 + Fraction`
  silently became a float, and so did the default `deltcon`'s `deltext(0.0,
  x)`. Both are now the integer `0`. The kernel only adds and compares times,
  so `int` and `Fraction` time stays exact end to end.
  - Floats are unchanged (`0 + 0.5 == 0.5`), and so are the example outputs,
    the trace digest and the TrackRailway digest.
  - Why it matters: PDEVS simultaneity is `==` on time. With floats,
    `0.1+0.1+0.1 ≠ 0.3`, so models that should be confluent run in separate
    rounds. `tests/test_robustness.py` demonstrates it: 4 rounds with floats,
    3 with `Fraction`.
  - The oracle runs 100 models with delays in thirds, which are inexact in
    binary. Kernel and reference agree, and every logged time stays
    `int`/`Fraction`. The first version of that test caught the default
    `deltcon`'s `0.0`.
- **C5, API cleanup.**
  - Removed the DEVSJAVA-style simulator getters that nothing used (`get_tn`,
    `equal_tn`, `get_tl`, `get_output`, `get_input`) and `Atomic.string_state`.
  - Kept the helpers the downstream projects use: `get_sigma`, `set_sigma`,
    `phase_is`, `get_model`.
  - Added the `py.typed` marker.

## Iteration 12: adaptive scheduler; copy contract and mypyc revisited (branch `perf/evaluate-remaining`)

The three levers left for last (A3, A6, A8), each measured before deciding.

### A6: adaptive scheduler (kept)

DEVStone is dense. In 20×20, 191 of 383 models are imminent each round, and
the heap (`heappop`/`heappush`, `_pop`) took about 15% of the time. A linear
scan, `min(map(attrgetter("t_n"), sims))` plus `[s for s in sims if s.t_n ==
t]`, costs about 0.05 µs per simulator per round. The heap costs about 0.27 µs
per reschedule. So the scan wins when n ≲ 5 × (reschedules per round), and
loses badly on large sparse models.

With `scheduler = "auto"` the coordinator counts reschedules and, every 64
rounds, picks one mode, with hysteresis: it switches to the scan if
n < 4.5k + 8 and back to the heap if n > 6.5k + 16. `"heap"` and `"scan"` force
a mode. Results are in `results/scheduler.jsonl` and come from
`benchmarks/scheduler_bench.py`; the table shows median ms:

| Case | heap | scan | auto |
|---|---|---|---|
| DEVStone 20×20 | 330.6 | 270.9 | **275.6** (−17%) |
| DEVStone 3×50 | 89.8 | 77.3 | **78.3** (−13%) |
| DEVStone 200×1 | 342.6 | 284.1 | **286.9** (−16%) |
| RL m=8, 200 episodes | 595.1 | 606.4 | 601.5 (+1%, noise) |
| RL m=64, 30 episodes | 627.8 | 617.1 | 613.5 (−2%) |
| Watchdog n=1000 | 411.6 | 321.1 | **333.1** (−19%) |
| Sparse n=64 | 28.2 | 93.6 | 27.3 |
| Sparse n=1024 | 32.0 | 1013.3 | 31.0 |
| Sparse n=4096 | 33.6 | 4099.6 | 32.5 |

`auto` is within 1–2% of the better mode in every case. A 256-round
adaptation period left 4–5% on the table in DEVStone, so it was shortened to
64. TrackRailway, with 9 atomics, runs in scan mode, is unchanged
(108.8/111.3 vs 111.0/110.5 ms per episode) and has an identical trajectory
digest.

**PDEVS argument.** The scan is the literal definition, tN = min tN_d and
IMM(t) = {d | tN_d = t}, in index order. The heap is an index over the same
values. Switching modes rebuilds the heap from the simulators' t_n, so no
event can be lost or duplicated across a switch.

**Validation.** The oracle runs the base comparison (300), the step API (150),
snapshot/restore (100) and variable structure (200) under three schedulers:
heap, scan, and "flip", which switches modes after every round. The mutation
check gains 2 scheduler mutations: switching without rebuilding the heap, and
a scan that also picks up models due within 0.25. All **19 are caught**.

### A8: no copy of routed lists (rejected)

Delivering the sender's list itself instead of `list(values)` saves 4.2–5.8%
(DEVStone 275.7 → 262.5, 77.7 → 73.9, 289.3 → 272.6 ms; RL m=8 613.5 → 587.8
ms). But fan-out would then share one list among receivers, so a model that
mutates its `x` corrupts its siblings' input, and a sender that reuses its
list rewrites delivered bags. The current contract allows both. That is not
worth 5%.

### A3: mypyc (unchanged verdict)

The earlier measurement (7–22%) stands. `deep_cloning()` still breaks under
mypyc. `snapshot()`/`restore()` don't, since they copy attributes by hand, but
per-platform wheels and CI would still be needed. Not pursued.

### Measurement incident: stale bytecode after `mutation_check.py`

The "default deltcon old e" mutation replaces `deltext(0, x)` with
`deltext(e, x)`. Since iteration 11 those two have **the same length**.
Restored within the same second, the file kept its size and mtime, so Python
kept executing the mutated `.pyc`.

- Detected when a test failed on a clean branch.
- The PR #12 commit and its verification predate that run, so they are
  unaffected.
- The first scan-prototype numbers in this iteration were taken with that
  stale code, and were **discarded**. Everything in the table above was
  re-measured after clearing `__pycache__`.
- `mutation_check.py` now runs its pytest subprocesses with
  `PYTHONDONTWRITEBYTECODE=1` and deletes the `.pyc` of every file it restores.

## Iteration 13: interpreters, measurement corrections, scheduler fix (branch `bench/interpreters`)

### A measurement error, and the corrected numbers

`run_devstone.py` and `run_rl.py` take `devspy=<repo root>` and add `src/`
themselves. In iterations 5, 7, 8 and 9, the before/after comparisons passed
`devspy=<worktree>/src`. The resulting `PYTHONPATH` pointed nowhere, so both
sides imported the installed devspy, which is the current tree, while the
label showed the base commit. **Those comparisons measured the same code
twice.** The runners now refuse any path that is not a repo root containing
`src/devspy/`.

Unaffected measurements:

- The watchdog and TrackRailway comparisons, which set `PYTHONPATH` directly.
- The scheduler comparison, which runs all modes in one process.
- A8, which edited the tree in place.

Every PR from #5 to #13 was re-measured from its own worktree in one session.
The final row (#15) was taken separately. Data is in `results/devstone.jsonl`
(tags `chain-remeasure` and `final-it13`) and `results/rl.jsonl`.

| PR | commit | DS 20×20 | DS 3×50 | DS 200×1 | RL m=8 ms/ep | RL m=64 ms/ep | RL P=16 eps/s |
|---|---|---|---|---|---|---|---|
| #5 dict bags | 23c78d0 | 312.2 | 86.4 | 319.3 | 3.16 | 26.71 | 2923 |
| #6 robustness | 4fd9a45 | 310.4 | 85.1 | 322.3 | 3.24 | 27.05 | 2907 |
| #7 oracle | fdb9757 | 314.7 | 84.6 | 319.8 | 3.25 | 26.92 | 2796 |
| #8 heap hygiene | 22780c0 | 323.1 | 87.7 | 327.1 | **2.80** | **22.22** | 3200 |
| #9 step API/observers | faab105 | 328.0 | 90.3 | 339.2 | 2.88 | 22.69 | 3280 |
| #10 variable structure | 1d1df69 | 326.5 | 89.1 | 339.2 | 2.91 | 22.96 | 3168 |
| #11 real time | f70ca94 | 329.1 | 90.6 | 335.8 | 2.89 | 22.57 | 3227 |
| #12 exact time | 91bcb6f | 323.4 | 89.7 | 341.4 | 2.94 | 22.66 | 3241 |
| #13 adaptive scheduler | 0a3ed23 | **274.8** | **77.6** | **283.5** | 3.10 | 22.52 | 3123 |
| #15 scheduler fix | 4f5e375 | 277.6 | 77.5 | 285.8 | 2.95 | 22.72 | 3071 |

What changes against the earlier claims:

- **#8 heap hygiene makes RL 14–17% faster.** It had been reported as "no
  change". RL resets every episode, and receivers rescheduled within an
  episode leave stale heap entries. The cost is 2–3% on DEVStone.
- **#9 observers cost 1.5–3.7%** on DEVStone and RL. That is one emptiness
  check per output and transition, plus extra locals. It is acceptable for
  the feature, but it is not "within noise" as reported.
- **#6, #7, #10, #11 and #12 are within noise**, so those claims hold now that
  they are measured properly.
- **#13 had a real regression of +4–6% on RL m=8**, found here. It is fixed in
  #15; see below.
- **Overall, #5 → #15:** DEVStone is 11–12% faster, RL m=8 7% faster, RL
  m=64 15% faster, and RL P=16 throughput 5% higher. All of this comes on top
  of the new features.
- **A7 re-measured** as a variant of the final tree, passing the full oracle,
  with 5 interleaved runs: RL m=8 −0.5%, DEVStone 20×20 +0.6%, 200×1 +0.4%.
  Rejecting it stands.

### Scheduler fix (#15)

The rule `n < 4.5·k + 8` always picked the scan for networks under about 10
models. For small sparse networks the heap wins: at n = 9 its operations
cost almost nothing. On top of that, the per-round accounting sat on the hot
path. The fix has three parts:

- **Rule:** scan when n / (k · log2 n) < 0.38, and back to the heap above
  0.46. The heap costs about k·log2 n per round and the scan about n.
- **Measured data:**

  | Case | Ratio | Better mode |
  |---|---|---|
  | DEVStone | 0.12 | scan |
  | Watchdog | 0.10 | scan |
  | RL m=64 | 0.33 | scan, by 2% |
  | RL m=8 | 0.50 | heap |
  | Sparse n=64 | 10.7 | heap |

- **No per-round cost:**
  - `next_tn` and `_pop` are bound per mode, so the hot path has no mode
    branch.
  - The round counter is a local in `_rounds`.
  - k comes from the growth of the simulators' version sum, since each
    reschedule bumps exactly one version.
  - Choices are made after 61, 122, 244, … rounds, capped at 8192, so the
    O(n) sum is amortized even for n = 4096. A first attempt that sampled a
    single round per period was too noisy for RL m=8.
  - The baseline restarts on `initialize`, `restore` and every restructure.

`scheduler_bench.py` results after the fix (`results/scheduler.jsonl`):

| Case | heap | scan | auto |
|---|---|---|---|
| DEVStone 20×20 | 325.5 | 269.5 | 271.5 |
| DEVStone 3×50 | 89.2 | 77.0 | 78.3 |
| DEVStone 200×1 | 339.8 | 288.1 | 288.4 |
| RL m=8 | 578.2 | 593.9 | 585.9 |
| RL m=64 | 626.3 | 614.8 | 626.0 |
| Watchdog | 405.3 | 318.0 | 334.9 |
| Sparse n=1024 | 29.5 | 995.9 | 30.1 |
| Sparse n=4096 | 31.2 | 4061.0 | 32.5 |

Process-separated comparisons against #12, interleaved:

| Workload | #12 | #15 | Change |
|---|---|---|---|
| RL m=8 (5 runs) | 2.925 | 2.944 | +0.6% |
| DEVStone 20×20 (5 runs) | 327.0 | 273.1 | −16.5% |
| TrackRailway, 5 trains (6 runs, mean) | 108.7 | 108.8 | 0% |

The oracle (heap, scan, flip), the 19 mutations, the trace digest and the
TrackRailway trajectory digest are all unchanged.

### Interpreters (A1, A2)

The same code (`8872fd0`, before the #15 fix) was run under four
interpreters: CPython 3.12 (reference) and PyPy 3.11 v7.3.22 from
downloads.python.org, and CPython 3.13.15 and 3.14.7 from python-build-standalone
20260924. Checksums were verified for all of them. Counters (transitions,
decisions, rewards) are identical across interpreters. Rows carry
`"python"`, and their labels end in `[cpython3.13]`, `[cpython3.14]` or
`[pypy3.11]`.

| | CPython 3.12 | CPython 3.13 | CPython 3.14 | PyPy 3.11 |
|---|---|---|---|---|
| DEVStone 5×3 (ms) | 22.4 | 22.9 | 19.5 | 13.5 |
| DEVStone 10×10 | 135.2 | 132.1 | 105.5 | 42.8 |
| DEVStone 200×1 | 286.4 | 279.3 | 221.8 | 84.7 |
| DEVStone 3×50 | 77.8 | 78.5 | 61.9 | 27.5 |
| DEVStone 20×20 | 275.4 | 276.7 | 217.4 | 93.1 (warm 88.8) |
| RL m=8 ms/ep (first episode) | 3.04 (3.3) | 2.87 (3.2) | 2.61 (2.9) | **0.76 (27.4)** |
| RL m=64 ms/ep (first episode) | 22.39 (22.8) | 22.70 (23.0) | 18.62 (18.9) | **5.62 (62.7)** |
| RL single-process RSS | 13 MiB | 15 MiB | 17 MiB | 72–93 MiB |
| RL P=16 eps/s (total RSS) | 2994 (208 MiB) | 3246 (240 MiB) | 3376 (267 MiB) | 2977 (1246 MiB) |

- **CPython 3.13** performs the same as 3.12.
- **CPython 3.14** is 14–21% faster for free, so it is the recommended
  version.
- **PyPy** is 3–4× faster in steady state, which puts DEVSpy at roughly
  2–3× adevs' times on DEVStone. It pays for that with JIT warmup (first
  episode 9× slower), 6–7× the memory, and no gain with 16 short-lived
  workers.
- PyPy suits long single-process simulations of models written in pure
  Python. RLDEVSpy and TrackRailway need PyTorch and NumPy, which PyPy can't
  run, so this doesn't apply to them.

## Iteration 2 backlog: features DEVSJAVA has and DEVSpy lacks

In order of relevance for this project:

1. ~~**Variable structure**~~ (done in iteration 9): adding or removing models and couplings at run time
   (`atomic.addModel/removeModel/addCoupling/removeCoupling`,
   `coordinator.setNewSimulator`, `updateChangedSimulators`). None of the
   RLDEVS4j projects use it.
2. ~~**Real-time simulation**~~ (done in iteration 10) (`model.simulation.realTime`: `RTcoordinator`,
   `atomicRTSimulator`, `TunableCoordinator`): pacing to the wall clock, and
   input injection from threads.
3. ~~**Activities**~~ (done in iteration 10, real time only) (`activity`, `holdIn(phase, sigma, activity)`): a threaded
   computation tied to a phase, whose result comes back as input.
4. GenCol collections (`Queue`, `Relation`, `Function`, `ZRelation`). Python's
   built-ins cover them, so this is low priority.
5. Distributed simulation (`model.simulation.distributed`). Declared out of
   scope.
