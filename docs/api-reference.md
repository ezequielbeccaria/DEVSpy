# API reference

Public symbols are re-exported from the top-level `devspy` package. For
narrative explanations see the guides: [Running simulations](running.md),
[Variable structure](variable-structure.md) and [Real time](real-time.md).

```python
from devspy import (
    Atomic, Digraph, Coupled, Couprel, Bag,
    DevsBase, IOBasicDevs,
    SimulationManager, Observer,
    NoModelSetError, ModelStructureError, ZeroTimeLoopError,
    AtomicSimulator, CoupledSimulator, Coordinator,
    TimeAtomicSimulator, TimeCoordinator,
    RealTimeRunner, WallClock, Activity,
)
```

---

## `SimulationManager`

The headless entry point. Wraps a `TimeAtomicSimulator` or `TimeCoordinator`
depending on what model you give it.

```python
SimulationManager(model=None)
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
f = SimulationManager(env)                  # a Digraph with input "action", output "obs"
obs = f.advance(stop_on_output=True)      # [(t, {"obs": [...]})]
f.inject("action", a)                     # at f.time, i.e. e = 0 after the observation
obs = f.advance(stop_on_output=True)
checkpoint = f.snapshot()                 # ... later: f.restore(checkpoint)
```

### Real time and activities

```python
runner = f.real_time(speed=1.0)            # simulated units per wall-clock second
threading.Thread(target=sensor_loop, args=(runner,)).start()   # calls runner.post(...)
outputs = runner.run(until=600.0, on_output=lambda t, y: actuate(y))
```

- `run(until, on_output)` paces the simulation: simulated time t is reached at
  wall time `start + (t - t0) / speed`. Root outputs are returned and also
  passed to `on_output` as they happen. If the host falls behind, due events
  run immediately and in order.
- `post(port, value)`, `post({port: [values]})` and `post(..., to=atomic)` can
  be called from any thread. The input is delivered at the simulated time that
  matches its arrival. An input that arrives exactly when an internal event is
  due goes in its own round right after that event, at the same t.
- `stop()` (any thread) ends the run.
- Inside a real-time run an atomic can call `self.start_activity(fn, *args,
  port="activity")`. `fn` runs in a thread, and its return value arrives later
  as external input on the model's `port`, like DEVSJAVA's activities. An
  exception in `fn` stops the run. `cancel()` on the returned `Activity`
  discards its result. In logical time, model a known duration with
  `hold_in` instead.
- Pass `clock=` (a `WallClock` subclass with `now()` and `wait(inbox, timeout)`)
  to run against a virtual clock in tests.

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

Variable structure, acting on the parent digraph and applied after the
current round:

```python
self.add_model(model)
self.remove_model(model_or_name)
self.add_coupling(src, src_port, dst, dst_port)      # models or names
self.remove_coupling(src, src_port, dst, dst_port)
```

Activities (real-time runs only):

```python
task = self.start_activity(fn, *args, port="activity", **kwargs)   # result arrives on `port`
task.cancel()
```

---

## `Digraph`

Coupled DEVS model.

```python
g = Digraph(name)
g.add(component)                                # Atomic or Digraph
g.add_coupling(src, src_port, dst, dst_port)    # models or names
g.remove(component_or_name)                     # also drops its couplings
g.remove_coupling(src, src_port, dst, dst_port)
g.add_inport(name)                              # for nested digraphs
g.add_outport(name)
g.get_components() / g.get_couprel()
```

### Variable structure

The calls above also work while the digraph is being simulated, from outside
(between `advance` calls) or from a model's transition. An atomic can use
`self.add_model(m)`, `self.remove_model(m_or_name)`,
`self.add_coupling(...)` and `self.remove_coupling(...)` on its parent digraph.
The semantics are DSDEVS:

- A change made during the round at `t` takes effect **after** that round, so
  every transition at `t` sees the old structure.
- New atomics are initialized at the current time (`manager.time`, the last
  event) and can be imminent in a following round at the same `t`.
- Removed atomics leave the schedule. Models that stay keep their state.
- The new network is validated. A rejected change made outside a round is
  undone and raises `ModelStructureError`. One made inside a round raises when
  the round ends.
- `reset()` re-initializes the current structure; it does not undo changes.
  `restore()` refuses a snapshot taken with a different structure.
- Editing `get_couprel()` directly bypasses all of this.

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

You normally don't construct these directly — `SimulationManager` does it.

| Class                  | Wraps                              | Key extra method                                   |
|------------------------|------------------------------------|----------------------------------------------------|
| `AtomicSimulator`      | `Atomic`                           | `simulate(num_iter)` — iteration-limited           |
| `Coordinator`          | `Digraph`                          | `simulate(num_iter)` — iteration-limited           |
| `TimeAtomicSimulator`  | `Atomic`                           | `simulate(time)`, `simulate_from_to(t0, t1)` (`simulate_until_time` is an alias) |
| `TimeCoordinator`      | `Digraph`                          | `simulate(max_sim_time)`, `simulate_from_to(t0, t1)`, `stop_simulation()` |
| `CoupledSimulator`     | `Atomic` (inside a `Coordinator`)  | internal — per-atomic state and precomputed routes |

Every `simulate*` loop initializes the simulator first if `initialize()` was
never called. Both `AtomicSimulator` and `Coordinator` also provide:

| Method / attribute | Effect |
|---|---|
| `inject_at(t, bag)` | Deliver `bag` on input ports at absolute time `t` (`t_l <= t <= t_n`). Confluent if `t == t_n`. |
| `sim_inject(e, port, value)` / `sim_inject(e, bag)` | Same, `e` after the last event. |
| `inject_to(model, t, bag)` | Deliver straight to an atomic's input ports (used for activity results). |
| `snapshot()` / `restore(s)` | What `SimulationManager.snapshot`/`restore` call. |
| `stop_simulation()` | End the running loop after the current round. |
| `observers` | The list of attached `Observer`s. |
| `max_rounds_per_instant` | Zero-time loop guard (default 100 000, `None` disables). |

`Coordinator.scheduler` (class or instance attribute) picks how the next
events are found:

- `"auto"` (default) measures the reschedules per round and picks the
  cheaper of the other two. The cost model is about n per round for the scan
  and k·log2 n for the heap.
- `"heap"` is a priority queue, best for sparse networks, where few models
  move per round compared with the network size.
- `"scan"` is a linear scan, best for dense networks, where a large share of
  the models move every round (about 16% faster on DEVStone).

All three give identical results.

---

## Exceptions

| Exception             | Raised when                                                   |
|-----------------------|---------------------------------------------------------------|
| `ModelStructureError` (a `ValueError`) | Building a coordinator for an invalid network: duplicate component names in a digraph (or a component named like its digraph), a coupling to an unknown component or an undeclared port, an input coupled straight to an output, or an atomic whose output reaches its own input (directly or through the hierarchy). |
| `ZeroTimeLoopError` (a `RuntimeError`) | A run spends more than `max_rounds_per_instant` rounds (default 100 000) at one simulated time, typically a `ta() == 0` loop. Set the attribute on the simulator (or class) to raise the limit, or to `None` to disable the check. |
| `ValueError`          | `sim_inject` outside `[0, t_n - t_l]` or on an undeclared input port. |
| `NoModelSetError`     | A manager method runs before any model was set.                |
