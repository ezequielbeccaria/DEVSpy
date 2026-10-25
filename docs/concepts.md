# DEVS concepts (cheat sheet)

DEVS (Discrete Event System Specification) describes a system as a set of
**atomic** state machines connected by **couplings** inside **coupled**
models. DEVSpy implements the *Parallel DEVS* (PDEVS) formalism: simultaneous
events are handled with a confluent transition (`deltcon`), all imminent
components emit in the same step (no `select` tie-breaking), and inputs
arrive as bags (`Message`).

## Atomic models

An atomic model has:

| Symbol      | Code                              | Meaning                                                  |
|-------------|-----------------------------------|----------------------------------------------------------|
| s           | `(self.phase, self.sigma)`        | state — a phase string plus a time-to-next-event float   |
| ta(s)       | `ta()` / returns `self.sigma`     | time advance — when the next internal event will happen  |
| δ_int(s)    | `deltint()`                       | internal transition (fires when `ta` elapses)            |
| δ_ext(s,e,x)| `deltext(e, x)`                   | external transition (fires when input arrives)           |
| δ_con(s,e,x)| `deltcon(e, x)`                   | confluent transition (input arrives at same time as int) |
| λ(s)        | `out()` returning a `Message`     | output function (called *just before* `δ_int`)           |

`e` is the time elapsed since the last transition.

### State helpers

```python
self.hold_in(phase, sigma)   # set state to (phase, sigma)
self.passivate()             # hold_in("passive", INFINITY)
self.passivate_in(phase)     # hold_in(phase, INFINITY)
self.cont(e)                 # decrement sigma by e (used in deltext to "continue")
self.phase_is(phase)         # bool
```

### Default `deltcon`

If you don't override it, `deltcon = deltint() then deltext(e, x)`. Note that
`e` is the elapsed time *before* `deltint` (i.e. `ta`), whereas Zeigler's
PDEVS default uses `e = 0` after the internal transition. When your
atomic tracks its own time (e.g., a clock variable or `cont(e)`), this default may
double-advance — the GPT example's `Transducer` shows how to override
explicitly.

## Coupled models (`Digraph`)

A `Digraph` holds a list of components (atomic or other digraphs) and a
`Couprel` of couplings:

```python
g = Digraph("system")
g.add(comp_a)
g.add(comp_b)
g.add_coupling(comp_a, "out", comp_b, "in")
```

To expose external ports on the digraph itself (so it can be embedded inside
another digraph):

```python
g.add_inport("in")
g.add_outport("out")
g.add_coupling(g, "in", comp_a, "in_port")     # external input → internal
g.add_coupling(comp_b, "out_port", g, "out")   # internal → external output
```

## Simulators

DEVSpy provides three simulator types — usually you don't touch them
directly because `DevsSuiteFacade` wraps the right one.

| Class                  | Wraps             | Public methods                                         |
|------------------------|-------------------|--------------------------------------------------------|
| `AtomicSimulator`      | one `Atomic`      | iteration-limited `simulate(num_iter)`                 |
| `Coordinator`          | one `Digraph`     | iteration-limited `simulate(num_iter)`                 |
| `TimeAtomicSimulator`  | one `Atomic`      | `simulate(t)`, `simulate_until_time(t)`                |
| `TimeCoordinator`      | one `Digraph`     | `simulate(max_sim_time)`, `stop_simulation()`          |
| `CoupledSimulator`     | atomic-in-digraph | internal — used by `Coordinator` for each child atomic |

## DEVS round in pictures

For each event time `t` the simulator does:

1. **`compute_input_output(t)`** — every component whose `t_n == t` emits via `out()`.
2. **route messages** — outputs are translated through the coupling relation and dropped into receivers' input bags.
3. **`wrap_deltfunc(t)`** — every component runs the appropriate transition:
   - input bag empty *and* `t == t_n` → `deltint()`
   - input bag non-empty *and* `t == t_n` → `deltcon(e, x)`
   - input bag non-empty *and* `t != t_n` → `deltext(e, x)`
4. **schedule next** — `t_l = t`, `t_n = t + ta()`.

`TimeCoordinator.simulate(t)` keeps doing this while `t_n <= t`.

## Further reading

- B. Zeigler, H. Praehofer, T. G. Kim — *Theory of Modeling and Simulation* (the canonical reference).
