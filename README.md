# DEVSpy

[![CI](https://github.com/ezequielbeccaria/DEVSpy/actions/workflows/ci.yml/badge.svg)](https://github.com/ezequielbeccaria/DEVSpy/actions/workflows/ci.yml)

A small, fast, pure-Python engine for [Parallel DEVS](https://en.wikipedia.org/wiki/DEVS)
(PDEVS) discrete-event simulation. It has no runtime dependencies and runs on
Python 3.9–3.14 and PyPy.

- **Parallel DEVS semantics**: confluent `deltcon` (Chow & Zeigler default),
  message bags, and no `select`. Every change is checked against a literal
  implementation of the PDEVS abstract simulator.
- **Fast flat kernel**: the coupling hierarchy is flattened once into direct
  routes, and an adaptive scheduler (heap or linear scan) finds imminent models.
  It is faster than PythonPDEVS's minimal kernel and DEVSJAVA (see
  [Performance](docs/performance.md)).
- **Drive it from outside**: `advance()` returns outputs, `inject()` delivers
  input at an exact time, `snapshot()`/`restore()` checkpoint in place, and
  observers watch every transition. This fits reinforcement-learning loops.
- **Variable structure (DSDEVS)**: models add and remove models and couplings
  while the simulation runs.
- **Real time**: runs can be paced by the wall clock, take thread-safe input,
  and run activities in background threads.
- **Exact time** with `int` or `fractions.Fraction`. Invalid networks and
  zero-time loops raise errors instead of misbehaving silently.

## Install

```bash
pip install git+https://github.com/ezequielbeccaria/DEVSpy.git
# or, for development
git clone https://github.com/ezequielbeccaria/DEVSpy.git && cd DEVSpy && poetry install
```

## Example

```python
from devspy import Atomic, DevsSuiteFacade, Digraph


class Source(Atomic):
    def __init__(self):
        super().__init__("source")
        self.add_outport("out")

    def initialize(self):
        self.n = 0
        self.hold_in("active", 1.0)

    def deltint(self):
        self.n += 1
        self.hold_in("active", 1.0)

    def out(self):
        return {"out": [self.n]}          # a bag: {output port: [values]}


class Doubler(Atomic):
    def __init__(self):
        super().__init__("doubler")
        self.add_inport("in")
        self.add_outport("out")

    def initialize(self):
        self.pending = []
        self.passivate()

    def deltext(self, e, x):
        self.pending = [2 * v for v in x["in"]]
        self.hold_in("reply", 0.5)

    def deltint(self):
        self.passivate()

    def out(self):
        return {"out": self.pending}


g = Digraph("pipeline")
g.add_outport("out")
src, dbl = Source(), Doubler()
g.add(src)
g.add(dbl)
g.add_coupling(src, "out", dbl, "in")
g.add_coupling(dbl, "out", g, "out")

f = DevsSuiteFacade(g)
print(f.advance(3.0))   # [(1.5, {'out': [0]}), (2.5, {'out': [2]})]
```

## Documentation

- [Getting started](docs/getting-started.md): first atomic and coupled models.
- [DEVS concepts](docs/concepts.md): the formalism as DEVSpy implements it.
- [Running simulations](docs/running.md): time limits, stepping, snapshots,
  observers, schedulers.
- [Variable structure](docs/variable-structure.md) and [Real time](docs/real-time.md).
- [Correctness](docs/correctness.md): the semantics, and how they are verified.
- [Performance](docs/performance.md): DEVSpy against other DEVS engines and
  Python interpreters.
- [API reference](docs/api-reference.md), [Examples](docs/examples.md),
  [Contributing](docs/contributing.md), [Changelog](CHANGELOG.md).

## Examples

```bash
poetry run python examples/gpt_model.py              # Generator -> Processor -> Transducer
poetry run python examples/mm1_queue.py              # M/M/1 queue with statistics
poetry run python examples/manufacturing_line.py     # hierarchical 3-station line
poetry run python examples/gym_loop.py               # agent outside the model, snapshot/restore
poetry run python examples/autoscaling.py            # servers added and removed at run time
poetry run python examples/real_time_thermostat.py   # wall-clock pacing, sensor thread, activity
```

## Scope

DEVSpy is the headless PDEVS simulation core. Distributed simulation and GUI
tooling are out of scope. It started as a port of the Java Devs-Suite-Facade
(DEVSJAVA) and has since moved to a flat event-driven kernel and plain-dict
message bags. `CHANGELOG.md` lists the breaking changes.

Apache-2.0 licensed.
