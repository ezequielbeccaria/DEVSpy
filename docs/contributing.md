# Contributing

## Dev setup

DEVSpy uses [Poetry](https://python-poetry.org/) for everything: virtualenv,
dependencies, build, publish.

```bash
git clone https://github.com/ezequielbeccaria/DEVSpy.git
cd DEVSpy
poetry install
```

This installs DEVSpy in editable mode plus the dev group (`pytest`, `ruff`).

Common commands:

```bash
poetry run pytest                  # run the test suite
poetry run pytest -k mm1           # run a subset
poetry run ruff check src tests    # lint
poetry run ruff format src tests   # format
poetry build                       # produce sdist + wheel under dist/
```

## Adding a dependency

```bash
poetry add <package>               # runtime dep
poetry add --group dev <package>   # dev-only dep
```

Commit the updated `pyproject.toml` *and* `poetry.lock` together.

## Project layout

```
DEVSpy/
├── docs/                # user documentation (this folder)
├── examples/            # runnable example models, each with tests
├── benchmarks/          # cross-engine benchmarks, trace diff, mutation check, FINDINGS.md
├── src/devspy/
│   ├── modeling/        # Atomic, Digraph, Couprel, Bag
│   ├── simulation/      # Coordinator (flat kernel), Time*, CoupledSimulator,
│   │                    # observer.py (observers, snapshots), real_time.py
│   ├── util/            # logging shim
│   ├── facade.py        # DevsSuiteFacade: the public entry point
│   └── exceptions.py
├── tests/               # pytest, one file per topic; reference_pdevs.py is the oracle
├── pyproject.toml       # Poetry-managed
└── poetry.lock
```

## Code style

- `ruff` with `line-length = 100`, `target-version = "py39"`.
- Public methods use `snake_case`. The canonical DEVS method names (`deltint`,
  `deltext`, `deltcon`, `ta`, `out`) stay verbatim, because that is how DEVS
  textbooks spell them.
- Avoid speculative abstractions. The hot path is `Coordinator._round`
  (`_pop`, `_lambda`, `_delta`). Measure before and after changing it, and
  keep log formatting behind `is_enabled`.

## Tests

Add a `test_*.py` under `tests/`. Tests for examples put `examples/` on
`sys.path`, as `tests/test_new_examples.py` does.

**Changing the kernel** (`src/devspy/simulation/`) has three requirements:

1. `poetry run pytest` must pass. It includes `tests/test_reference_pdevs.py`,
   which compares the kernel with the literal PDEVS abstract simulator in
   `tests/reference_pdevs.py` on hundreds of random models. Never change the
   oracle to make the kernel pass.
2. `poetry run python benchmarks/mutation_check.py` must report every mutation
   as `CAUGHT`. If you add a feature, add a mutation that breaks it.
3. `benchmarks/trace_diff.py --model-level` must give byte-identical output
   between the old and new engine, or the difference must be explained by a
   PDEVS argument in `benchmarks/FINDINGS.md`.

## Benchmarks

```bash
python benchmarks/run_devstone.py devspy=/path/to/old/checkout devspy=$PWD --tag my-change
python benchmarks/run_rl.py devspy=/path/to/old/checkout devspy=$PWD
python benchmarks/scheduler_bench.py
```

`devspy=` takes a **repo root**; the runners refuse anything else. Results
are appended to `benchmarks/results/*.jsonl`, and conclusions go in
`benchmarks/FINDINGS.md`. Run a runner with a different interpreter to
benchmark that interpreter; rows record which one was used.
`benchmarks/README.md` explains how to set up the other engines (DEVSJAVA,
xDEVS, PythonPDEVS, adevs, Cadmium).

## Releasing

1. Update `CHANGELOG.md` and bump `version` in `pyproject.toml` and
   `src/devspy/__init__.py`.
2. Check that CI is green on `main`.
3. `poetry build`, then `poetry publish` (PyPI credentials are configured with
   `poetry config`).
