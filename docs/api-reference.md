# API reference

Public symbols are re-exported from the top-level `devspy` package.

```python
from devspy import (
    Atomic, Digraph, Coupled, Couprel,
    Port, Content, Message,
    Entity, IntEnt, DoubleEnt, Pair,
    DevsBase, IOBasicDevs,
    DevsSuiteFacade, NoModelSetError,
    AtomicSimulator, CoupledSimulator, Coordinator,
    TimeAtomicSimulator, TimeCoordinator,
)
```

---

## `DevsSuiteFacade`

The headless entry point. Wraps a `TimeAtomicSimulator` or `TimeCoordinator`
depending on what model you give it.

```python
DevsSuiteFacade(model=None)
```

Accepts an `Atomic`, a `Digraph`, a preconfigured `TimeCoordinator`, or `None`
(set later with `set_atomic_model` / `set_digraph_model`).

| Method                                   | Effect                                                          |
|------------------------------------------|-----------------------------------------------------------------|
| `set_atomic_model(model)`                | Wraps the atomic model in a `TimeAtomicSimulator` and initializes to t=0. |
| `set_digraph_model(model, initialize=True)` | Wraps the digraph in a `TimeCoordinator`. (When called via the constructor, `initialize=False` is used to match Java's behavior — call `reset()` explicitly.) |
| `reset()`                                | Re-initializes the simulator to t=0.                            |
| `simulate_iterations(n)`                 | Runs the iteration-count simulator (`Coordinator.simulate(n)`). |
| `simulate_to_time(t)`                    | Runs until simulated time reaches `t`.                          |
| `simulate_to_time(t0, t1)`               | Initializes at `t0` then simulates to `t1`.                     |
| `deep_cloning()`                         | Returns a `copy.deepcopy` of the underlying simulator.          |
| `is_simulation_done()`                   | True once a `simulate_*` call has returned.                     |
| `get_simulator()`                        | The underlying simulator instance.                              |

Raises `NoModelSetError` if a `simulate_*` is called before any model is set.

---

## `Atomic`

Subclass to define your own atomic models.

```python
class Atomic(IOBasicDevs):
    name: str
    phase: str = "passive"
    sigma: float = INFINITY
```

Override these:

| Method                  | When called                                              |
|-------------------------|----------------------------------------------------------|
| `initialize()`          | Once, before simulation starts. Set initial phase/sigma. |
| `deltint()`             | When `t == t_n` and no input is pending.                 |
| `deltext(e, x)`         | When input arrives and `t != t_n`.                       |
| `deltcon(e, x)`         | When input arrives at `t == t_n`. Default = `deltint()` then `deltext(e, x)`. |
| `out() -> Message`      | Just before `deltint`/`deltcon`. Return what to emit.    |

State helpers (already implemented):

```python
self.hold_in(phase, sigma)
self.passivate()
self.passivate_in(phase)
self.cont(e)
self.phase_is(phase) -> bool
self.get_phase() / self.get_sigma()
```

Port management (inherited from `DevsBase`):

```python
self.add_inport(name)
self.add_outport(name)
self.get_inports() / self.get_outports()
```

---

## `Digraph`

Coupled DEVS model.

```python
g = Digraph(name)
g.add(component)                                # Atomic or Digraph
g.add_coupling(src, src_port, dst, dst_port)    # both can be Atomic or Digraph
g.add_inport(name)                              # for nested digraphs
g.add_outport(name)
g.get_components() / g.get_couprel()
```

---

## `Port`, `Content`, `Message`

```python
Port(name)                       # an in/out port reference
Content(port, value)             # one tagged value
Message()                        # multiset of Content (a "bag")
m.add(content)
m.is_empty()
m.values_on_port(port_name) -> list
for c in m: ...                  # iterate Contents
```

`port` may be a `Port` instance or a string (auto-promoted).

---

## Entities — `Entity`, `IntEnt`, `DoubleEnt`, `Pair`

Lightweight value wrappers, ported from DEVSJAVA's `GenCol`. Use them for
parity; in Python any object works as a `Content` value.

```python
IntEnt(value)         # name auto-generated from int(value)
DoubleEnt(value)
Pair(key, value)      # NamedTuple — used internally by Couprel
```

---

## Simulators

You normally don't construct these directly — `DevsSuiteFacade` does it.

| Class                  | Wraps                              | Key extra method                                   |
|------------------------|------------------------------------|----------------------------------------------------|
| `AtomicSimulator`      | `Atomic`                           | `simulate(num_iter)` — iteration-limited           |
| `Coordinator`          | `Digraph`                          | `simulate(num_iter)` — iteration-limited           |
| `TimeAtomicSimulator`  | `Atomic`                           | `simulate(time)` (parity quirk; see note), `simulate_until_time(t)`, `simulate_from_to(t0, t1)` |
| `TimeCoordinator`      | `Digraph`                          | `simulate(max_sim_time)`, `simulate_from_to(t0, t1)`, `stop_simulation()` |
| `CoupledSimulator`     | `Atomic` (inside a `Coordinator`)  | internal — handles message routing per atomic      |

### Quirk preserved from Java

`TimeAtomicSimulator.simulate(time)` in DEVSJAVA gates on the iteration count
(`while i <= time`) rather than simulated time. DEVSpy preserves that exact
semantic for parity. If you want a real time gate, use
`simulate_until_time(t)`. `TimeCoordinator.simulate(t)` correctly gates on
`t_n <= t`.

---

## Exceptions

```python
NoModelSetError  # raised by DevsSuiteFacade.simulate_* when no model is set
```
