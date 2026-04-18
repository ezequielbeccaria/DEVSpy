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
├── docs/                # markdown docs (this folder)
├── examples/            # runnable example models
├── src/devspy/
│   ├── modeling/        # Atomic, Digraph, Port, Content, Message, entities
│   ├── simulation/      # AtomicSimulator, Coordinator, Time*, CoupledSimulator
│   ├── util/            # logging shim
│   ├── facade.py
│   └── exceptions.py
├── tests/               # pytest tests, one file per topic
├── pyproject.toml       # Poetry-managed
└── poetry.lock
```

## Code style

- `ruff` with `line-length = 100`, `target-version = "py39"`.
- Public methods use `snake_case`; DEVS canonical method names (`deltint`,
  `deltext`, `deltcon`, `ta`, `out`) are kept verbatim because that is how
  every DEVS textbook spells them.
- Avoid speculative abstractions — the engine is small and the hot loop is
  in `Coordinator.compute_input_output` / `wrap_deltfunc`; keep them simple.

## Adding a new test

Drop a `test_*.py` under `tests/`. If the test runs an example script, add
the example folder to `sys.path` like the existing `test_mm1_queue.py` does:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))
from mm1_queue import run
```

## Java parity

If you change anything in `simulation/` or `modeling/`, double-check that
the [Java mapping](java-mapping.md) page still matches and that the
behavioural quirks listed there are still preserved (the existing tests
will catch most regressions, but the parity page is the source of truth).

## Releasing

1. Bump `version` in `pyproject.toml` (`poetry version patch|minor|major`).
2. `poetry build`.
3. `poetry publish` (requires PyPI credentials configured via `poetry config`).
