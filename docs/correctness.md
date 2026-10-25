# Correctness

DEVSpy aims to *be* Parallel DEVS, not merely to behave the same way from one
version to the next. This page states the semantics it implements and how they
are checked.

## Semantics

**The round.** For each event time `t` the coordinator runs the PDEVS abstract
simulator of Chow & Zeigler (1994) on the flattened network:

1. IMM(t) = { d | t_n(d) = t }. Each imminent model's λ runs once, and its
   outputs are routed to the receivers' input bags. A bag is a multiset per
   port, and each receiver gets its own lists.
2. Each model in IMM(t) ∪ { d | x_d ≠ ∅ } then takes exactly one transition.
   It is `deltint` if it is imminent with no input, `deltext(e, x)` if it has
   input and is not imminent, and `deltcon(e, x)` if both. No other model is
   touched.
3. Each transitioned model is rescheduled: t_l = t, t_n = t + ta(s).

**Default `deltcon`** is δcon(s, x) = δext(δint(s), 0, x). After the internal
transition no time has elapsed in the new state. DEVSJAVA and DEVSpy < 0.3
passed the old `e`; xDEVS, adevs, Cadmium and PythonPDEVS use 0.

**Networks** must be coupled DEVS models:

- EIC goes from digraph inputs to component inputs, EOC from component outputs
  to digraph outputs, and IC from component outputs to component inputs.
- All couplings connect declared ports.
- Component names are unique within a digraph.
- No model may influence itself (i ∉ I_i). This is checked on the flattened
  network, so a digraph-level `d -> d` coupling is fine when it only connects
  distinct atomics inside `d`.

**Legitimacy.** A legitimate DEVS model makes finitely many transitions in
any finite interval. More than `max_rounds_per_instant` rounds at one instant
raise `ZeroTimeLoopError`.

**External input** at time `t` requires t_l ≤ t ≤ t_n, which is the abstract
simulator's synchronization check. At t = t_n it is a confluent round: λ
first, then δcon.

**Dynamic structure** follows DSDEVS (Barros), as described in
[Variable structure](variable-structure.md). **Real time** changes only *when*
rounds run; see [Real time](real-time.md) for the one policy choice it
forces.

**Time** is compared with `==`, so use `int` or `Fraction` when events must
coincide exactly. Floats work, but `0.1 + 0.1 + 0.1 != 0.3`.

**Determinism.** Models are processed in a fixed depth-first order, and bags
are filled in a fixed coupling order. DEVSJAVA keeps child simulators in a
`HashSet`, so its order can change between runs; both are valid PDEVS.
PythonPDEVS's super-dense time can split simultaneous arrivals at a later `t`
into separate bags. DEVSpy delivers them in one bag, which is the classic
PDEVS behaviour.

## How it is verified

**A reference simulator as oracle.** `tests/reference_pdevs.py` is an
independent, literal implementation of the hierarchical abstract simulator:

- one coordinator per digraph;
- no flattening, heap or caching;
- couplings translated level by level at every round;
- DSDEVS re-reading of the structure after each round.

`tests/test_reference_pdevs.py` runs the real kernel and the oracle on
hundreds of random hierarchical models, with ties, zero-time advances, default
and custom `deltcon`, `cont(e)`, multi-port fan-in and fan-out, random
injections (many of them confluent), exact `Fraction` time, models that add
and remove siblings, snapshots, observers and real-time runs. Each model logs
its own view of every transition: clock, kind, `e`, and the input bag as a
multiset. The logs, and the root outputs, must be identical. Everything also
runs under each scheduler (heap, scan, and a mode that switches every round).

**The oracle is tested too.** It reproduces the hand-derived trace of the GPT
model. `benchmarks/mutation_check.py` injects 19 known kernel bugs one at a
time, and the oracle must catch all of them. The bugs include confluent
dispatched as `deltext`, receivers left without δ, stale heap entries,
injections without λ, structure changes applied mid-round, a broken scheduler
switch, and real-time inputs delivered at the wrong time.

**Trace diffs** (`benchmarks/trace_diff.py --model-level`) record the full λ/δ
trace of the examples, DEVStone and 200 random models, so that two engine
versions can be compared byte for byte. Every kernel change ships with a
PDEVS argument and this diff; the reasoning is logged in
`benchmarks/FINDINGS.md`.

**Downstream.** `benchmarks/downstream/trackrailway_trace.py` checks that real
RL episodes of RLDEVSpy-TrackRailway produce identical trajectories across
engine versions.

**CI** runs lint, the full suite (oracle included) on CPython 3.9–3.13 and
PyPy 3.11, a check that PyPy and CPython produce the same λ/δ trace digest, and
the mutation check.
