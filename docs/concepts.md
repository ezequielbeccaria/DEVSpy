# DEVS concepts (cheat sheet)

DEVS (Discrete Event System Specification) describes a system as a set of
**atomic** state machines connected by **couplings** inside **coupled**
models. DEVSpy implements the *Parallel DEVS* (PDEVS) formalism: simultaneous
events are handled with a confluent transition (`deltcon`), all imminent
components emit in the same step (no `select` tie-breaking), and inputs
arrive as bags, which are plain dicts of `{port: [values]}`.

## Atomic models

An atomic model has:

| Symbol      | Code                              | Meaning                                                  |
|-------------|-----------------------------------|----------------------------------------------------------|
| s           | `(self.phase, self.sigma)`        | state — a phase string plus a time-to-next-event float   |
| ta(s)       | `ta()` / returns `self.sigma`     | time advance — when the next internal event will happen  |
| δ_int(s)    | `deltint()`                       | internal transition (fires when `ta` elapses)            |
| δ_ext(s,e,x)| `deltext(e, x)`                   | external transition (fires when input arrives)           |
| δ_con(s,e,x)| `deltcon(e, x)`                   | confluent transition (input arrives at same time as int) |
| λ(s)        | `out()` returning `{port: [values]}` | output function (called *just before* `δ_int`)        |

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

If you don't override it, `deltcon(e, x) = deltint(); deltext(0, x)`: the
Parallel DEVS default δcon(s, x) = δext(δint(s), 0, x). The input arrives just
after the internal transition, so no time has elapsed in the new state.
(DEVSpy < 0.3 passed the pre-`deltint` `e`, as DEVSJAVA does, which made
`cont(e)` or a clock variable advance twice.) Override it when the two
transitions should not compose that way.

### Time values

Simultaneity is decided with `==` on time values, so float rounding can split
events that should coincide: `0.1 + 0.1 + 0.1 != 0.3`, so a model stepping by
0.1 and one stepping by 0.3 never fire together. Times start at the integer
`0`, and the kernel only adds and compares them, so you can use `int` or
`fractions.Fraction` for `sigma` and get exact time. `Fraction(1, 10) * 3 ==
Fraction(3, 10)`. `math.inf` still means passive.

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
| `CoupledSimulator`     | atomic-in-digraph | internal — per-atomic state driven by `Coordinator`    |

A `Coordinator` flattens the whole `Digraph` hierarchy when it is built. Every
coupling path, however many levels it crosses, becomes a direct route from an
atomic output port to atomic input ports. Nesting digraphs therefore costs
nothing at run time.

## DEVS round in pictures

For each event time `t` the simulator does:

1. **`compute_input_output(t)`** — the imminent components (`t_n == t`, taken from an event heap) emit via `out()`.
2. **route messages** — outputs follow the precomputed routes into the receivers' input bags.
3. **`wrap_deltfunc(t)`** — the imminent components and the receivers run the appropriate transition; no other component is touched:
   - input bag empty *and* `t == t_n` → `deltint()`
   - input bag non-empty *and* `t == t_n` → `deltcon(e, x)`
   - input bag non-empty *and* `t != t_n` → `deltext(e, x)`
4. **schedule next** — `t_l = t`, `t_n = t + ta()`.

`TimeCoordinator.simulate(t)` keeps doing this while `t_n <= t`.

## Further reading

- B. Zeigler, H. Praehofer, T. G. Kim — *Theory of Modeling and Simulation* (the canonical reference).
