# DEVSpy

Python 3 port of [Devs-Suite-Facade](https://github.com/ezequielbeccaria/Devs-Suite-Facade): a small, headless engine for simulating discrete-event systems written in [DEVS](https://en.wikipedia.org/wiki/DEVS) form, with both iteration- and time-limited runs.

## Install

```bash
poetry install                # uses Poetry (recommended)
# or
pip install .                 # plain pip, no dev tools
```

## Hello, atomic

```python
from devspy import Atomic, Content, DevsSuiteFacade, IntEnt, Message


class Beeper(Atomic):
    def __init__(self):
        super().__init__("beeper")
        self.add_outport("beep")

    def initialize(self):
        self.hold_in("active", 1.0)

    def deltint(self):
        self.hold_in("active", 1.0)

    def out(self):
        m = Message()
        m.add(Content("beep", IntEnt(1)))
        return m


facade = DevsSuiteFacade(Beeper())
facade.reset()
facade.simulate_to_time(5.0)
```

## Documentation

Full docs live in [`docs/`](docs/index.md):

- [Getting started](docs/getting-started.md) — install, first models, run the examples.
- [DEVS concepts](docs/concepts.md) — the formalism in two pages.
- [API reference](docs/api-reference.md) — every public class and method.
- [Examples](docs/examples.md) — walk-through of `gpt_model`, `mm1_queue`, `manufacturing_line`.
- [Java mapping](docs/java-mapping.md) — what each Java type / method became.
- [Contributing](docs/contributing.md) — dev setup with Poetry, tests, code style.

## Examples

```bash
poetry run python examples/gpt_model.py            # Generator → Processor → Transducer
poetry run python examples/mm1_queue.py            # M/M/1 queue with statistics
poetry run python examples/manufacturing_line.py   # 3-station hierarchical line
```

## Scope

Ports the headless DEVS simulation core. Not ported: DEVSJAVA's `GenCol` legacy collections (replaced by Python built-ins), distributed RMI-style simulation, and SimView GUI hooks. See [Java mapping](docs/java-mapping.md) for the full breakdown.
