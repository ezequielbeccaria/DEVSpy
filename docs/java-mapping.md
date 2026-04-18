# Java → Python mapping

DEVSpy is a from-scratch Python port of [Devs-Suite-Facade](https://github.com/ezequielbeccaria/Devs-Suite-Facade) (which itself wraps DEVSJAVA 2.7). Most types map straightforwardly; this page is the cheat sheet.

## Public facade

| Java                                        | Python                                       |
|---------------------------------------------|----------------------------------------------|
| `DevsSuiteFacade`                           | `DevsSuiteFacade`                            |
| `simulateIterations(n)`                     | `simulate_iterations(n)`                     |
| `simulateToTime(t)`                         | `simulate_to_time(t)`                        |
| `simulateToTime(t0, t1)`                    | `simulate_to_time(t0, t1)`                   |
| `reset()`                                   | `reset()`                                    |
| `deepCloning()` (Apache Commons Lang)       | `deep_cloning()` (`copy.deepcopy`)           |
| `setAtomicModel` / `setDigraphModel`        | `set_atomic_model` / `set_digraph_model`    |
| `NoModelSettedException`                    | `NoModelSetError`                            |

## Modeling

| Java                                           | Python                                       |
|------------------------------------------------|----------------------------------------------|
| `atomic` (class)                               | `Atomic`                                     |
| `digraph` / `Coupled` / `Components`           | `Digraph` / `Coupled`                        |
| `couprel` (multi-relation)                     | `Couprel`                                    |
| `port` / `PortInterface`                       | `Port`                                       |
| `content`                                      | `Content`                                    |
| `message` / `MessageInterface` (a `Bag`)       | `Message` (list-backed multiset)             |
| `IOBasicDevs` / `IODevs` / `devs`              | `IOBasicDevs` / `DevsBase`                   |
| `holdIn(p, σ)` / `passivate()` / `phaseIs(p)`  | `hold_in(p, σ)` / `passivate()` / `phase_is(p)` |
| `Continue(e)` (named `Continue` to avoid Java keyword) | `cont(e)`                            |
| `deltint` / `deltext` / `deltcon` / `ta` / `out` | same names — DEVS canon, kept as-is        |
| `computeInputOutput(t)` / `wrapDeltfunc(t)`    | `compute_input_output(t)` / `wrap_deltfunc(t)` |

## Simulation

| Java                                | Python                              |
|-------------------------------------|-------------------------------------|
| `atomicSimulator`                   | `AtomicSimulator`                   |
| `coordinator`                       | `Coordinator`                       |
| `coupledSimulator`                  | `CoupledSimulator`                  |
| `TimeAtomicSimulator` (facade pkg)  | `TimeAtomicSimulator`               |
| `TimeCoordinator`     (facade pkg)  | `TimeCoordinator`                   |

## Entities (GenCol minimal subset)

DEVSJAVA brings a whole `GenCol` package of generic collections. DEVSpy keeps
only the four types that coupling/content actually depend on; everything else
is replaced by Python built-ins.

| Java                          | Python                                            |
|-------------------------------|---------------------------------------------------|
| `GenCol.Pair<K,V>`            | `Pair(key, value)` (NamedTuple)                   |
| `GenCol.entity`               | `Entity` (base dataclass)                         |
| `GenCol.intEnt`               | `IntEnt`                                          |
| `GenCol.doubleEnt`            | `DoubleEnt`                                       |
| `GenCol.Bag` / `ensembleBag`  | Python `list` (multiset semantics)                |
| `GenCol.Queue` / `ensembleList` | `collections.deque` where needed                |

## Other one-offs

| Java                                          | Python                              |
|-----------------------------------------------|-------------------------------------|
| `DevsInterface.INFINITY`                      | `math.inf`                          |
| `org.apache.commons.lang3.SerializationUtils.clone` | `copy.deepcopy`               |
| `util.Logging` (full / partial)               | thin wrapper over stdlib `logging`  |
| `synchronized` methods                        | dropped — Python sims are single-threaded |
| `Runnable` / threaded coordinator             | dropped — distributed sim not ported |
| SimView GUI hooks (`startActivity`, `wrapDeltfuncHook2`, …) | no-op methods kept for parity |

## Behavioural quirks preserved verbatim

- `TimeAtomicSimulator.simulate(time)` in Java gates on the iteration counter (`while i <= time`), not on simulated time. DEVSpy keeps that exact semantic; for a real time gate use `simulate_until_time(t)`.
- `TimeCoordinator.simulate(maxSimTime)` correctly gates on `t_n <= maxSimTime`.
- `DevsSuiteFacade(atomic)` initializes the simulator to t=0 in the constructor; `DevsSuiteFacade(digraph)` does **not** — call `reset()` explicitly, matching the Java asymmetry.

## Things deliberately dropped

- Distributed simulation (RMI client/server simulators).
- GUI utilities (`HtmlUtil`, `WindowUtil`, `PointUtil`, `ComponentUtil`, `OldModelConverter`).
- `GenCol` legacy collection classes beyond the four entities above.
- Real-time / tunable coordinators.
