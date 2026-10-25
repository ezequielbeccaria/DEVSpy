# API reference

Public symbols are re-exported from the top-level `devspy` package.

```python
from devspy import (
    Atomic, Digraph, Coupled, Couprel, Bag,
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
| `set_digraph_model(model, initialize=True)` | Wraps the digraph in a `TimeCoordinator`. When invoked through the constructor, `initialize=False` — call `reset()` explicitly before simulating. |
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
| `out() -> Bag`          | Just before `deltint`/`deltcon`. Return what to emit.    |

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

## Messages: `Bag`

A message bag is a plain dict, `Bag = dict[str, list]`, that maps a port name to
the values on that port at one instant. Values are ordinary Python objects;
there are no wrapper classes.

```python
def deltext(self, e, x):            # x: Bag of the inputs received
    for job in x.get("in", ()):     # values that arrived on port "in"
        ...
    if "stop" in x:                 # did anything arrive on "stop"?
        ...

def out(self):                      # return a Bag; {} means no output
    return {"out": [self.job], "next": [1]}
```

- A bag is a multiset. The order of values within one port is the order
  in which they were delivered. There is no ordering across ports.
- Every receiver gets its own lists, so a model may mutate `x`. A model
  may also reuse the lists it returns from `out()`.
- `Couprel` stores couplings as `(component, port)` tuples:
  `g.get_couprel().translate("src", "out") -> {("sink", "in"), ...}`.
- `sim_inject(e, port, value)` or `sim_inject(e, {port: [values]})` injects
  external input.

---

## Simulators

You normally don't construct these directly — `DevsSuiteFacade` does it.

| Class                  | Wraps                              | Key extra method                                   |
|------------------------|------------------------------------|----------------------------------------------------|
| `AtomicSimulator`      | `Atomic`                           | `simulate(num_iter)` — iteration-limited           |
| `Coordinator`          | `Digraph`                          | `simulate(num_iter)` — iteration-limited           |
| `TimeAtomicSimulator`  | `Atomic`                           | `simulate(time)` (iteration-gated; see note), `simulate_until_time(t)`, `simulate_from_to(t0, t1)` |
| `TimeCoordinator`      | `Digraph`                          | `simulate(max_sim_time)`, `simulate_from_to(t0, t1)`, `stop_simulation()` |
| `CoupledSimulator`     | `Atomic` (inside a `Coordinator`)  | internal — per-atomic state and precomputed routes |

### `TimeAtomicSimulator.simulate(time)` is iteration-gated

For backwards-compatibility, `TimeAtomicSimulator.simulate(time)` loops
`while i <= time` where `i` is the iteration counter — not the simulated
time. Use `simulate_until_time(t)` for a real time gate.
`TimeCoordinator.simulate(t)` does gate on simulated time (`t_n <= t`).

---

## Exceptions

```python
NoModelSetError  # raised by DevsSuiteFacade.simulate_* when no model is set
```
