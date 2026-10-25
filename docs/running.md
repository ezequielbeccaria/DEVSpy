# Running simulations

`DevsSuiteFacade` wraps an atomic model or a `Digraph` and offers several ways
to run it. All of them follow the same Parallel DEVS round: λ for the imminent
models, routing, then δ for the imminent models and the receivers.

## Time and iteration limits

```python
f = DevsSuiteFacade(model)
f.reset()                       # initialize at t = 0 (optional: the first run does it)
f.simulate_to_time(100.0)       # every event with t_n <= 100
f.simulate_to_time(0.0, 50.0)   # re-initialize at t0, run to t1
f.simulate_iterations(10)       # at most 10 rounds
```

Root outputs (the root digraph's output ports) are printed by these methods.
To get them as data instead, use `advance`.

## Stepping from outside (gym-style)

```python
outputs = f.advance(until=10.0)            # [(t, {port: [values]}), ...], nothing printed
outputs = f.advance(stop_on_output=True)   # up to and including the next round with root output
f.inject("action", 3)                      # input on a root input port at f.time (e = 0)
f.inject({"action": [3, 4]}, at=12.5)      # at an absolute time; earlier rounds run first
f.time, f.next_event_time                  # last event time; next internal event (inf if none)
```

`inject(..., at=t)` first runs every round strictly before `t`, then delivers
the input at `t`. If `t` is also an internal event time, the two form one
**confluent** round: the imminent models emit first, then take `deltcon`. Both
methods return the root outputs of the rounds they ran.

This is the shape of an RL loop where the agent lives outside the model (see
`examples/gym_loop.py`):

```python
[(t, obs)] = f.advance(stop_on_output=True)
f.inject("action", policy(obs))
```

## Snapshots

```python
checkpoint = f.snapshot()   # every model's attributes, the times, the schedule
...
f.restore(checkpoint)       # back to that state, in place; repeatable
```

Restoring is **in place**: your references to model objects stay valid. Model
attributes are deep-copied, together with anything they reference (RNGs,
buffers, other objects), except other models, digraphs and simulators, which
are kept by reference. `restore` refuses a snapshot taken before a structure
change. `deep_cloning()` is different: it returns an independent copy of the
whole simulator, with new model objects.

## Observers

```python
from devspy import Observer

class Trace(Observer):
    def on_output(self, t, model, y):
        print(t, model.get_name(), "emits", y)

    def on_transition(self, t, model, kind, e, x):   # kind: "int" | "ext" | "con"
        print(t, model.get_name(), kind, e, x)

f.add_observer(Trace())
```

`on_transition` runs right after each transition. With no observer attached
the kernel only pays an emptiness check.

## Schedulers

The coordinator finds the next event either with a heap or with a linear scan
over the models. With `Coordinator.scheduler = "auto"` (the default) it
measures how many models are rescheduled per round and picks the cheaper one:

- **scan** for dense models, where many models move every round
  (DEVStone-like: about 16% faster);
- **heap** for large sparse ones (up to 120× faster than the scan there).

Force one with `Coordinator.scheduler = "heap"` or `"scan"`, on the class or
on a simulator. The results are identical in every mode.

## Logging

DEVSpy logs through the standard `logging` module under the `devspy` logger.
Iteration-level traces are emitted at `DEBUG` level:

```python
import logging
logging.basicConfig()
logging.getLogger("devspy").setLevel(logging.DEBUG)
```

## Errors

| Exception | When |
|---|---|
| `ModelStructureError` | Invalid network: duplicate names, couplings to unknown components or undeclared ports, input coupled straight to output, a model coupled to itself |
| `ZeroTimeLoopError` | More than `max_rounds_per_instant` (100 000) rounds at one time: a model that never advances time |
| `ValueError` | `inject`/`sim_inject` outside `[t_l, t_n]` or on an undeclared port |
| `NoModelSetError` | A facade method called before a model was set |
