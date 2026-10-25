# Getting started

## Install

DEVSpy is managed with [Poetry](https://python-poetry.org/).

```bash
git clone https://github.com/ezequielbeccaria/DEVSpy.git
cd DEVSpy
poetry install
```

This creates a virtualenv with DEVSpy plus the dev tooling (`pytest`, `ruff`).
Run any DEVSpy script through `poetry run`:

```bash
poetry run python examples/gpt_model.py
poetry run pytest
```

If you only want to use DEVSpy as a dependency (no dev tools):

```bash
pip install .
```

## A minimal atomic model

An atomic model defines a `(phase, sigma)` state and the four DEVS transition
functions: `initialize`, `deltint`, `deltext`, `out` (and optionally `deltcon`).

```python
from devspy import Atomic, Bag, DevsSuiteFacade


class Beeper(Atomic):
    def __init__(self) -> None:
        super().__init__("beeper")
        self.add_outport("beep")
        self._count = 0

    def initialize(self) -> None:
        self._count = 0
        self.hold_in("active", 1.0)  # fire every 1.0 time units

    def deltint(self) -> None:
        self._count += 1
        self.hold_in("active", 1.0)

    def out(self) -> Bag:
        return {"beep": [self._count + 1]}


facade = DevsSuiteFacade(Beeper())
facade.reset()
facade.simulate_to_time(5.0)
```

## A minimal coupled model

A coupled model is a `Digraph` with components and couplings between their ports:

```python
from devspy import Atomic, DevsSuiteFacade, Digraph


class Source(Atomic):
    def __init__(self):
        super().__init__("source")
        self.add_outport("out")

    def initialize(self):
        self.hold_in("emit", 1.0)

    def deltint(self):
        self.hold_in("emit", 1.0)

    def out(self):
        return {"out": [1]}


class Sink(Atomic):
    def __init__(self):
        super().__init__("sink")
        self.add_inport("in")
        self.received = 0

    def initialize(self):
        self.received = 0
        self.passivate()

    def deltext(self, e, x):
        # x maps each input port to the values that arrived on it at this instant
        self.received += len(x.get("in", ()))


src, snk = Source(), Sink()
g = Digraph("pipeline")
g.add(src)
g.add(snk)
g.add_coupling(src, "out", snk, "in")

facade = DevsSuiteFacade(g)
facade.reset()
facade.simulate_to_time(10.0)
print(snk.received)  # ~10
```

## Running the bundled examples

```bash
poetry run python examples/gpt_model.py            # Generator → Processor → Transducer
poetry run python examples/mm1_queue.py            # M/M/1 queue with statistics
poetry run python examples/manufacturing_line.py   # 3-station hierarchical line
```

See [Examples](examples.md) for what each one demonstrates.
