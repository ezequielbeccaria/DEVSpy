# Variable structure

Models and couplings can be added and removed while a simulation runs, either
from outside (between `advance` calls) or from inside a model's transition.

```python
class Factory(Atomic):
    def deltint(self):
        worker = Worker(f"w{self.n}")
        self.add_model(worker)                          # into this model's parent digraph
        self.add_coupling(self, "job", worker, "in")    # models or names
        self.remove_model("w0")                         # also drops its couplings
        self.remove_coupling(self, "job", "w1", "in")
        ...
```

From outside, use the parent digraph directly: `g.add(m)`, `g.remove(m_or_name)`,
`g.add_coupling(...)`, `g.remove_coupling(...)`. See `examples/autoscaling.py`
for a dispatcher that grows and shrinks a server pool.

## Semantics (DSDEVS)

DEVSpy follows Barros' Dynamic Structure DEVS:

- **A change made during the round at `t` takes effect after that round.** Every
  transition at `t` sees the structure that was in force when the round began,
  and the outputs of `t` are routed by it. (Applying changes mid-round would
  make a model's input depend on the order in which its siblings transition.)
- **New atomics** are initialized at the current time (`facade.time`, the
  time of the last event). They can be imminent in a later round at the same
  `t`.
- **Removed atomics** leave the schedule. Models that stay keep their state
  and their scheduled events.
- **The new network is validated** with the same rules as at construction. A
  rejected change made outside a round is undone and raises
  `ModelStructureError`. One made inside a round raises when the round ends,
  and the coordinator rolls back to the previous network.

## Notes

- `reset()` re-initializes the *current* structure. It does not undo changes.
- `restore()` refuses a snapshot taken with a different structure.
- Editing `g.get_couprel()` directly bypasses the coordinator. Use the
  `Digraph` methods.
- Each change re-flattens the network. That is O(network size), which is fine
  for occasional changes and expensive if a model restructures on every event.
