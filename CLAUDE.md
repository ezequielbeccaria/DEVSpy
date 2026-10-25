# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

DEVSpy is a small, headless, pure-Python (3.9+, no runtime deps) engine for Parallel DEVS (PDEVS) discrete-event simulation: confluent `deltcon`, no `select`, message bags. It began as a port of the Java Devs-Suite-Facade / DEVSJAVA, which is why many docstrings say "Ports X". Distributed simulation and GUI tooling are out of scope.

## Commands

Everything goes through Poetry:

```bash
poetry install                              # editable install + dev group (pytest, ruff)
poetry run pytest                           # full suite
poetry run pytest tests/test_facade.py      # one file
poetry run pytest -k mm1                    # by keyword / single test name
poetry run ruff check src tests             # lint (line-length 100, target py39)
poetry run ruff format src tests
poetry run python examples/mm1_queue.py     # also gpt_model.py, manufacturing_line.py
poetry build
```

When adding a dependency, commit `pyproject.toml` and `poetry.lock` together.

Any change to `simulation/` must keep DEVS semantics. `tests/test_reference_pdevs.py` checks the kernel against `tests/reference_pdevs.py`, a literal hierarchical PDEVS abstract simulator (Chow & Zeigler), on hundreds of random models, with and without external injections. Never change the oracle to make the kernel pass. Also run the trace diff in `benchmarks/README.md`: the λ/δ traces of the old and new engine must be byte-identical. Performance work is measured with the `benchmarks/run_*.py` runners, which append to `benchmarks/results/*.jsonl`. Log conclusions in `benchmarks/FINDINGS.md`.

## Architecture

The code is split into two parallel trees: **modeling** (what the user writes) and **simulation** (what drives it).

- `modeling/`: `DevsBase` → `IOBasicDevs` (the abstract DEVS contract: `initialize`, `deltint`, `deltext`, `deltcon`, `ta`, `out`, `show_state`) → `Atomic`, which keeps state as `(phase, sigma)` with helpers like `hold_in` and `passivate`. `Digraph` is the coupled model. It holds components and a `Couprel`, which maps a `(src_name, src_port)` tuple to a set of `(dst_name, dst_port)` tuples. **Couplings are keyed by component name, not object identity**, so component names must be unique within a digraph. Message bags are plain dicts, `Bag = dict[str, list]` (port → values), and values are plain Python objects. Models read inputs with `x.get("in", ())` and return `{"out": [v]}` (or `{}`) from `out()`. Since 0.2.0 there are no `Message`/`Content`/`IntEnt` wrappers.
- `simulation/`: there is a simulator class hierarchy, and every class in it is built on `AtomicSimulator`:
  - `AtomicSimulator` runs one atomic model. It owns `t_l` and `t_n`, and `wrap_deltfunc` decides between deltint, deltext and deltcon.
  - `Coordinator(AtomicSimulator)` runs a `Digraph` hierarchy as a **flat** set of `CoupledSimulator`s, one per atomic, created in depth-first component order. There are no nested coordinators: the hierarchy is only a modelling construct.
    - At construction, `_flatten` resolves every coupling path through EIC/IC/EOC levels into `CoupledSimulator.fanout`: for each output port, a list of `(dst_port, [target sims])`. A `None` target is an output port of the root digraph. Couplings from a digraph input straight to its own output are dropped.
    - A heap of `(t_n, index, version)` with lazy invalidation gives the next event time. Each round has two phases. `_round(t)` (used by the `simulate` loops) pops IMM(t), runs λ (`_lambda`, which copies the values into a fresh list per receiver and port), and then runs δ (`_delta`) on IMM(t) ∪ INF(t) in index order and reschedules them. `compute_input_output` and `wrap_deltfunc` expose the same two phases separately for `sim_inject`. When a model doesn't override `ta()`, `sigma` is read directly (`CoupledSimulator.ta_is_sigma`).
    - `reset()` re-initializes the atomics and rebuilds the heap without re-flattening.
    - Variable structure: `Digraph` mutators call `coordinator.structure_changed()`. Inside a run or δ phase (`_running`) the change is deferred, and `_restructure()` runs after the round. It re-flattens while reusing existing `CoupledSimulator`s (state kept, indices reassigned), initializes new atomics at `t_l`, and rebuilds the heap. On a `ModelStructureError` it rolls back.
  - `CoupledSimulator(AtomicSimulator)` is the per-atomic record that the coordinator drives (`t_l`, `t_n`, input bag, `fanout`, `index`, `version`). It has no loop of its own.
  - `TimeAtomicSimulator` and `TimeCoordinator` add time-limited runs.
  - `observer.py`: `Observer` (`on_output`, `on_transition`), which `_lambda`/`_delta` notify only `if observers:`, plus the snapshot helpers. A snapshot deep-copies model attributes but keeps models, digraphs and simulators by reference.
  - `real_time.py`: `RealTimeRunner` paces `_run(1, t_next)` against a `WallClock`. Other threads only touch its `queue.Queue` inbox (`post`, `stop`, activity results). Inputs are delivered with `inject_at`/`inject_to` at the clock's simulated time, clamped to `[t_l, t_n]`, and always after the due events.
  - Root outputs go through `show_output()`. It prints them, or appends `(t, bag)` to `_sink` when the facade's `advance`/`inject` are collecting them. `inject_at(t, bag)` takes an absolute time, so it does not drift through `t_l + e`.
- `facade.py`: `DevsSuiteFacade` is the public entry point. It wraps an `Atomic` in a `TimeAtomicSimulator`, or a `Digraph` in a `TimeCoordinator`. Its `simulate_iterations` calls the **base-class** `simulate(num_iter)` directly to skip the time-based override.

### Semantics to keep in mind (0.3.0 dropped the DEVSJAVA parity quirks)

- `Coordinator` validates the network while flattening and raises `ModelStructureError`: unique component names per digraph, couplings only between declared ports (EIC/IC/EOC), no input-to-output coupling, and no atomic whose output reaches its own input. Models must `add_inport`/`add_outport` every port they couple.
- Run loops (`_run`) initialize on first use. `DevsSuiteFacade(digraph)` itself does not initialize, so "construct, `reset()`, simulate" initializes exactly once (TrackRailway's RNG streams depend on that). Every `simulate*` gates on simulated time, except the iteration-count `simulate(num_iter)` of the base classes.
- More than `max_rounds_per_instant` (100 000) consecutive rounds at one time raise `ZeroTimeLoopError`.
- The default `deltcon` is `deltint(); deltext(0, x)` (Chow & Zeigler). `sim_inject` raises `ValueError` outside `[0, t_n - t_l]` or on undeclared ports.
- Logging goes through `util/logging.py`, a thin shim over the `devspy` stdlib logger. Java's `FULL`/`PARTIAL` levels map to `DEBUG`/`INFO`.

## Conventions

- DEVS method names (`deltint`, `deltext`, `deltcon`, `ta`, `out`) stay verbatim. Everything else is `snake_case`.
- The hot loop is `Coordinator.compute_input_output` / `wrap_deltfunc`. Keep it simple and avoid speculative abstractions. Any change to a simulator's `t_n` must bump `version` and push a new heap entry; stale entries are skipped. Only imminent models get λ, and only imminent models or those with input get δ. Reset (`initialize`) must only call `initialize()` on atomics, in component order: RLDEVSpy-TrackRailway relies on that order.
- Never format log messages unconditionally in hot paths. Guard them with `devspy.util.logging.is_enabled(level)`.
- Tests are one file per topic under `tests/`. Example-driven tests import the example's `run()` and assert on the event traces it records. Some do `from examples.gpt_model import run` (this relies on pytest putting the repo root on `sys.path`). Others insert `examples/` into `sys.path` first. `tests/test_parity_gpt.py` is the reference trace for the Generator → Processor → Transducer model.
- User-facing docs are in `docs/` (concepts, API reference, examples). Update `docs/api-reference.md` when the public API in `src/devspy/__init__.py` changes.
