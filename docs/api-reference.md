# API reference

Public symbols are re-exported from the top-level `devspy` package.

```python
from devspy import (
    Atomic, Digraph, Coupled, Couprel, Bag,
    DevsBase, IOBasicDevs,
    DevsSuiteFacade, NoModelSetError, ModelStructureError, ZeroTimeLoopError,
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
| `set_digraph_model(model, initialize=True)` | Wraps the digraph in a `TimeCoordinator` (validating its structure). Through the constructor, `initialize=False`: the first `reset()` or `simulate_*()` initializes. |
| `reset()`                                | Re-initializes the simulator to t=0.                            |
| `simulate_iterations(n)`                 | Runs the iteration-count simulator (`Coordinator.simulate(n)`). |
| `simulate_to_time(t)`                    | Runs every event with `t_n <= t` (atomic and digraph models alike). |
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
| `deltcon(e, x)`         | When input arrives at `t == t_n`. Default = `deltint()` then `deltext(0, x)`. |
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
  external input `e` after the last event. It raises `ValueError` unless
  `0 <= e <= t_n - t_l` and every port is a declared input port.

---

## Simulators

You normally don't construct these directly — `DevsSuiteFacade` does it.

| Class                  | Wraps                              | Key extra method                                   |
|------------------------|------------------------------------|----------------------------------------------------|
| `AtomicSimulator`      | `Atomic`                           | `simulate(num_iter)` — iteration-limited           |
| `Coordinator`          | `Digraph`                          | `simulate(num_iter)` — iteration-limited           |
| `TimeAtomicSimulator`  | `Atomic`                           | `simulate(time)`, `simulate_from_to(t0, t1)` (`simulate_until_time` is an alias) |
| `TimeCoordinator`      | `Digraph`                          | `simulate(max_sim_time)`, `simulate_from_to(t0, t1)`, `stop_simulation()` |
| `CoupledSimulator`     | `Atomic` (inside a `Coordinator`)  | internal — per-atomic state and precomputed routes |

Every `simulate*` loop initializes the simulator first if `initialize()` was
never called.

---

## Exceptions

| Exception             | Raised when                                                   |
|-----------------------|---------------------------------------------------------------|
| `ModelStructureError` (a `ValueError`) | Building a coordinator for an invalid network: duplicate component names in a digraph (or a component named like its digraph), a coupling to an unknown component or an undeclared port, an input coupled straight to an output, or an atomic whose output reaches its own input (directly or through the hierarchy). |
| `ZeroTimeLoopError` (a `RuntimeError`) | A run spends more than `max_rounds_per_instant` rounds (default 100 000) at one simulated time, typically a `ta() == 0` loop. Set the attribute on the simulator (or class) to raise the limit, or to `None` to disable the check. |
| `ValueError`          | `sim_inject` outside `[0, t_n - t_l]` or on an undeclared input port. |
| `NoModelSetError`     | A facade method runs before any model was set.                |
