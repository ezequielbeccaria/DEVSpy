# DEVSpy

Python 3 port of [Devs-Suite-Facade](https://github.com/ezequielbeccaria/Devs-Suite-Facade): headless DEVS simulation with support for both iteration-limited and time-limited runs.

## Install

```bash
pip install -e .
# or with dev tooling
pip install -e '.[dev]'
```

## Usage

Define a model by subclassing `Atomic` or `Digraph`, then drive it through `DevsSuiteFacade`:

```python
from devspy import DevsSuiteFacade, Atomic

class MyModel(Atomic):
    def __init__(self):
        super().__init__("my_model")
        self.add_outport("out")

    def initialize(self):
        self.hold_in("active", 1.0)

    def deltint(self):
        self.passivate()

    def out(self):
        from devspy.modeling import Message, Content, IntEnt
        m = Message()
        m.add(Content("out", IntEnt(42)))
        return m

facade = DevsSuiteFacade(MyModel())
facade.reset()
facade.simulate_to_time(10.0)
```

See `examples/gpt_model.py` for a full Generator → Processor → Transducer coupled model.

## Mapping to the Java facade

| Java | Python |
|---|---|
| `DevsSuiteFacade` | `DevsSuiteFacade` |
| `simulateIterations(n)` | `simulate_iterations(n)` |
| `simulateToTime(t)` | `simulate_to_time(t)` |
| `simulateToTime(t0, t1)` | `simulate_to_time(t0, t1)` |
| `reset()` | `reset()` |
| `deepCloning()` | `deep_cloning()` |
| `atomic` / `digraph` | `Atomic` / `Digraph` |
| `TimeAtomicSimulator` / `TimeCoordinator` | `TimeAtomicSimulator` / `TimeCoordinator` |

## Scope

Ports the headless simulation core. Not ported: DEVSJAVA's `GenCol` legacy collections (replaced by Python built-ins), distributed RMI-style simulation, and SimView GUI hooks.
