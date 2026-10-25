# DEVSpy documentation

DEVSpy is a small, fast, pure-Python engine for Parallel DEVS (PDEVS)
discrete-event simulation.

## Guides

- [Getting started](getting-started.md): installing, a first atomic model, a
  first coupled model.
- [DEVS concepts](concepts.md): atomic and coupled models, transitions, bags,
  time, and the simulation round.
- [Running simulations](running.md): time and iteration limits, gym-style
  stepping (`advance`/`inject`), snapshots, observers, schedulers, errors.
- [Variable structure](variable-structure.md): adding and removing models and
  couplings at run time (DSDEVS).
- [Real time](real-time.md): wall-clock pacing, thread-safe input, activities.

## Reference

- [API reference](api-reference.md): every public class and method.
- [Examples](examples.md): walkthroughs of the scripts in `examples/`.
- [Correctness](correctness.md): the exact semantics, and how they are verified
  (reference-simulator oracle, mutation check, trace diffs).
- [Performance](performance.md): DEVSpy against PythonPDEVS, xDEVS, DEVSJAVA,
  adevs and Cadmium, and across interpreters.
- [Contributing](contributing.md): development setup, tests, benchmarks,
  releases.
- [Changelog](../CHANGELOG.md) and the full engineering log,
  [`benchmarks/FINDINGS.md`](../benchmarks/FINDINGS.md).

Source: [github.com/ezequielbeccaria/DEVSpy](https://github.com/ezequielbeccaria/DEVSpy)
