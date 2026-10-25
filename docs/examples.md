# Examples

Three runnable scripts live in `examples/`. Each is a complete, self-contained
DEVS model with a `run()` function and a `__main__` entry point.

```bash
poetry run python examples/<script>.py
```

---

## 1. `gpt_model.py` — Generator → Processor → Transducer

The canonical DEVS smoke test.

- **Generator**: emits a job every `GEN_PERIOD` time units.
- **Processor**: takes `PROCESS_TIME` to complete a job; drops jobs that arrive while busy.
- **Transducer**: observes arrivals and completions; sends a `stop` signal back to the generator after `OBS_TIME`.

`Transducer.deltcon` is overridden explicitly. Since 0.3 the default
(`deltint(); deltext(0, x)`) does the same thing; DEVSpy < 0.3 passed the
pre-`deltint` `e` and double-advanced the transducer's clock (the GPT example is
where this was first hit).

Output: prints two lists of `(time, job_id)` for arrivals and completions.

---

## 2. `mm1_queue.py` — M/M/1 queue with statistics

Single-server queueing system with **Poisson arrivals** (rate `λ`) and
**exponential service** (rate `μ`).

Components:

- **Generator** — exponential inter-arrival times via `random.expovariate(λ)`.
- **Queue** — FIFO buffer; pushes head to server when server is free, otherwise enqueues.
- **Server** — exponential service via `random.expovariate(μ)`; signals queue for next job.
- **Statistics** — records arrivals/departures and computes:
  - utilization = `busy_time / sim_time`
  - mean wait W = mean of `departure_time - arrival_time` per job
  - mean L = `λ × W` (Little's Law)
  - theoretical ρ = `λ / μ` for comparison.

Default run (λ=1.0, μ=1.5, t=1000) prints something like:

```
M/M/1 results (lambda=1.0, mu=1.5, t=1000.0):
  arrivals      : 965
  departures    : 964
  rho (theory)  : 0.6667
  utilization   : 0.6406
  mean wait W   : 1.8261
  mean L = lam*W: 1.8261
```

The corresponding tests (`tests/test_mm1_queue.py`) assert observed
utilization ≈ ρ and mean wait ≈ `1/(μ - λ)`.

---

## 3. `manufacturing_line.py` — Hierarchical assembly line

Three-station serial assembly line. **Each station is itself a `Digraph`**
containing a `Buffer` and a `Machine`, so the top-level `Line` is a
*digraph of digraphs*. The coordinator flattens it into direct routes between
atomics. This is the example to run when you want to exercise nested-coupling
routing in the engine.

Topology:

```
PartGenerator ─▶ Station1 ─▶ Station2 ─▶ Station3 ─▶ Collector

Station_i:  in ─▶ Buffer ─▶ Machine ─▶ out
                        ◀──next──┘
```

Default run uses service times `(0.8, 1.5, 0.7)` with arrivals every 1.0
time unit. Station2 saturates first because it is the slowest. Output:

```
Manufacturing line results:
  sim time            : 200.0
  parts generated     : 200
  parts completed     : 131
  throughput (parts/t): 0.6550
  bottleneck station  : station2
  per-station:
    station1: util=0.796  processed=199  max_buf=0
    station2: util=0.990  processed=132  max_buf=66
    station3: util=0.459  processed=131  max_buf=0
```

Throughput is bounded by `1 / max(service_time)` ≈ 0.667; Station2's buffer
piles up because it is the bottleneck; Station3 is starved.

The tests (`tests/test_manufacturing_line.py`) assert that the bottleneck
moves correctly when the slowest station changes, and that an underloaded
line tracks the arrival rate.
