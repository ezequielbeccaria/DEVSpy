# API reference

Public symbols are re-exported from the top-level `devspy` package.

```python
from devspy import (
    Atomic, Digraph, Coupled, Couprel, Bag,
    DevsBase, IOBasicDevs,
    DevsSuiteFacade, Observer,
    NoModelSetError, ModelStructureError, ZeroTimeLoopError,
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
| `advance(until=inf, stop_on_output=False)` | Runs every round with `t_n <= until` and **returns** the root outputs as `[(t, bag), ...]` instead of printing them. With `stop_on_output=True` it returns after the first round with root output. |
| `inject(port, value, at=None)` / `inject({port: [values]}, at=None)` | Runs the rounds strictly before `at` (default: `time`), then injects the input at `at`. If `at` is also an internal event time, both are one confluent round (λ of the imminents first). Returns the root outputs of the rounds it ran. |
| `time`, `next_event_time`                | Time of the last event or injection; time of the next internal event (`inf` if none). |
| `add_observer(obs)`, `remove_observer(obs)` | Attach or detach an `Observer` (see below).                  |
| `snapshot()`, `restore(snapshot)`        | Copy the whole simulation state, and later put it back **in place**: the model objects stay the same, while their attributes (and anything they reference except other models) are copied. A snapshot can be restored many times. |
| `deep_cloning()`                         | Returns a `copy.deepcopy` of the underlying simulator (new model objects). |
| `is_simulation_done()`                   | True once a `simulate_*` call has returned.                     |
| `get_simulator()`                        | The underlying simulator instance.                              |

Raises `NoModelSetError` if a `simulate_*` is called before any model is set.

### Driving a simulation from outside (gym-style)

```python
f = DevsSuiteFacade(env)                  # a Digraph with input "action", output "obs"
obs = f.advance(stop_on_output=True)      # [(t, {"obs": [...]})]
f.inject("action", a)                     # at f.time, i.e. e = 0 after the observation
obs = f.advance(stop_on_output=True)
checkpoint = f.snapshot()                 # ... later: f.restore(checkpoint)
```

### `Observer`

Subclass `devspy.Observer` and override what you need:

```python
class Trace(Observer):
    def on_output(self, t, model, y): ...                 # a model's λ produced y
    def on_transition(self, t, model, kind, e, x): ...    # kind: "int" | "ext" | "con"
```

`on_transition` runs right after the transition. `e` is the elapsed time the
model received; for `"int"` it is the time since the model's last transition.
`x` is its input bag (`{}` for `"int"`). With no observer attached the kernel
only pays an emptiness check.

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
