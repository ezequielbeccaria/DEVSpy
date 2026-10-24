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

## Architecture

The code is split into two parallel trees: **modeling** (what the user writes) and **simulation** (what drives it).

- `modeling/`: `DevsBase` → `IOBasicDevs` (the abstract DEVS contract: `initialize`, `deltint`, `deltext`, `deltcon`, `ta`, `out`, `show_state`) → `Atomic`, which keeps state as `(phase, sigma)` with helpers like `hold_in` and `passivate`. `Digraph` is the coupled model. It holds components and a `Couprel`, which maps `Pair(src_name, src_port)` to a set of `Pair(dst_name, dst_port)`. **Couplings are keyed by component name, not object identity**, so component names must be unique within a digraph. Messages are `Message` bags of `Content(port, value)`. Values are usually `Entity` subclasses (`IntEnt`, `DoubleEnt`, `Pair`).
- `simulation/`: there is a simulator class hierarchy, and every class in it is built on `AtomicSimulator`:
  - `AtomicSimulator` runs one atomic model. It owns `t_l` and `t_n`, and `wrap_deltfunc` decides between deltint, deltext and deltcon.
  - `CoupledSimulator(AtomicSimulator)` runs an atomic model that sits inside a digraph. It translates its outputs through its local coupling info and calls `put_messages` on sibling simulators. If the destination is not a sibling, the message bubbles up to the parent through `put_my_messages`.
  - `Coordinator(AtomicSimulator)` runs a `Digraph`. It creates a `CoupledSimulator` for each atomic child and a nested `Coordinator` for each digraph child. Its `t_n` is the minimum over its children. Each round has two phases: `compute_input_output` (every child calls `out()`, then `send_messages` routes the results) and `wrap_deltfunc` (external input is pushed down through `ext_coup_info`, then every child runs `delt_func`). Couplings that start at the digraph itself go into `ext_coup_info`. All other couplings are given to the source child's simulator through `add_pair`.
  - `TimeAtomicSimulator` and `TimeCoordinator` add time-limited runs.
- `facade.py`: `DevsSuiteFacade` is the public entry point. It wraps an `Atomic` in a `TimeAtomicSimulator`, or a `Digraph` in a `TimeCoordinator`. Its `simulate_iterations` calls the **base-class** `simulate(num_iter)` directly to skip the time-based override.

### Parity quirks to keep in mind

- `TimeAtomicSimulator.simulate(time)` gates on the **iteration counter** (`i <= time`), not on simulated time, to match the Java behaviour. This means `facade.simulate_to_time(t)` on an *atomic* model runs about `t` iterations. `simulate_until_time` is the version that gates on time. `TimeCoordinator.simulate` gates on time correctly.
- `DevsSuiteFacade(digraph)` does **not** initialize, matching Java. Call `facade.reset()` before simulating. `set_digraph_model` initializes by default.
- The default `deltcon` runs `deltint()` and then `deltext(e, x)` with the pre-`deltint` `e` (Zeigler's PDEVS default uses `e = 0`). Models that track their own clock should override it (see `Transducer` in `examples/gpt_model.py`).
- Logging goes through `util/logging.py`, a thin shim over the `devspy` stdlib logger. Java's `FULL`/`PARTIAL` levels map to `DEBUG`/`INFO`.

## Conventions

- DEVS method names (`deltint`, `deltext`, `deltcon`, `ta`, `out`) stay verbatim. Everything else is `snake_case`.
- The hot loop is `Coordinator.compute_input_output` / `wrap_deltfunc`. Keep it simple and avoid speculative abstractions.
- Tests are one file per topic under `tests/`. Example-driven tests import the example's `run()` and assert on the event traces it records. Some do `from examples.gpt_model import run` (this relies on pytest putting the repo root on `sys.path`). Others insert `examples/` into `sys.path` first. `tests/test_parity_gpt.py` is the reference trace for the Generator → Processor → Transducer model.
- User-facing docs are in `docs/` (concepts, API reference, examples). Update `docs/api-reference.md` when the public API in `src/devspy/__init__.py` changes.
