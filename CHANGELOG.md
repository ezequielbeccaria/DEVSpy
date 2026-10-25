# Changelog

## 0.3.0

Drops the remaining DEVSJAVA parity quirks in favour of Parallel DEVS semantics
and fails loudly on invalid models.

### Breaking

- The default `Atomic.deltcon(e, x)` is now `deltint(); deltext(0, x)`, the
  Chow & Zeigler default δcon(s, x) = δext(δint(s), 0, x). It used to pass the
  pre-`deltint` `e`. Only models that use the default `deltcon` and read `e` in
  `deltext` (for example with `cont(e)`) behave differently.
- `Coordinator` validates the network and raises `ModelStructureError` for:
  - duplicate component names in a digraph, or a component named like its digraph;
  - couplings to unknown components or to undeclared ports (every coupled port
    must be declared with `add_inport`/`add_outport`);
  - an input coupled straight to an output (previously ignored silently);
  - an atomic whose output reaches its own input, directly or through the hierarchy.
- `TimeAtomicSimulator.simulate(time)`, and therefore
  `DevsSuiteFacade.simulate_to_time(t)` on an atomic model, now runs the events
  with `t_n <= time`. It used to compare the iteration counter with `time`.
- `sim_inject` raises `ValueError` when `e` is outside `[0, t_n - t_l]` or a port
  is not a declared input port. It used to drop the input silently.

### Fixed

- `sim_inject` at exactly `t_n` (and any `wrap_deltfunc` without a preceding
  `compute_input_output`) now runs λ for the imminent models and routes their
  outputs before δ. It used to apply δ without λ, so those outputs were lost.
  The root outputs of an injected round are shown, as in a normal round.

### Added: driving and observing a simulation

- `DevsSuiteFacade.advance(until, stop_on_output)`: run, and return the root
  outputs as `(t, bag)` pairs instead of printing them.
- `DevsSuiteFacade.inject(port, value, at=None)`: inject at an absolute time
  (default: now). A confluent round if `at` is an event time.
- `time` and `next_event_time` properties.
- `Observer` with `on_output` and `on_transition`; `add_observer` and
  `remove_observer`.
- `snapshot()` / `restore()` on the facade and the simulators. Restoring
  happens in place, and a snapshot can be restored repeatedly.
- `inject_at(t, bag)` on the simulators, the absolute-time form of `sim_inject`.

### Performance

- The coordinator rebuilds its event heap when stale entries pile up (more than
  `2·n + 64` entries), and a receiver whose next event time does not move keeps
  its heap entry. Models whose inputs keep pushing timeouts later (watchdogs)
  run 28–34% faster with bounded memory. Other workloads are unchanged.

### Added

- `tests/reference_pdevs.py`: a literal PDEVS abstract simulator used as an
  oracle (450 random-model comparisons in the test suite), and
  `benchmarks/mutation_check.py`, which shows the oracle catches known kernel bugs.
- `ZeroTimeLoopError`: raised after more than `max_rounds_per_instant`
  (default 100 000, `None` disables it) consecutive rounds at one time.
- Every `simulate*` loop initializes the simulator if `initialize()` was never
  called, so `DevsSuiteFacade(digraph).simulate_to_time(t)` no longer silently
  does nothing.
- `Coordinator.stop_simulation()` (it was only on `TimeCoordinator`).

## 0.2.0

- Message bags are plain dicts, `{port: [values]}`. `Message`, `Content`, `Port`,
  `Entity`, `IntEnt`, `DoubleEnt` and `Pair` are removed. `Couprel` stores
  `(component, port)` tuples.
- Flat event-driven coordinator: the hierarchy is flattened at construction, with
  a heap of next-event times. 4–25× faster than 0.1.
