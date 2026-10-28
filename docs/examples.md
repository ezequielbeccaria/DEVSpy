# Examples

Six runnable scripts live in `examples/`. Each is a complete, self-contained
DEVS model with a `run()` function and a `__main__` entry point, and each has
tests under `tests/`.

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

---

## 4. `gym_loop.py`: an agent outside the model

A water tank with random inflow and an outflow valve. The **agent is ordinary
Python code** outside the DEVS model, as in a gym-style RL loop:

```python
[(t, obs)] = manager.advance(stop_on_output=True)   # run to the next observation
manager.inject("valve", policy(obs["level"][0]))    # answer at the same instant
```

After a warm-up the script takes a `snapshot()`, then runs two policies
(proportional and bang-bang) from that same state with `restore()`, and
compares how well they hold the level at 50:

```
from the same checkpoint at t=10, 50 steps each (ends at t=60.0):
  mean |level - 50.0| proportional: 6.87
  mean |level - 50.0| bang-bang   : 8.36
```

---

## 5. `autoscaling.py`: variable structure

A dispatcher receives bursty jobs and keeps a queue. When the queue grows it
adds a `Server` model and couples it (`add_model`, `add_coupling`). When a
server stays idle for a while, it removes it (`remove_model`). The pool grows
to 6 servers in each burst and shrinks back to 1 in the quiet phases:

```
servers created: 10, peak pool: 6, final pool: 1
  t=  0.048  servers=1
  t=  2.032  servers=2
  ...
  t= 29.385  servers=1
```

Changes made inside a transition take effect after the current round, as in
DSDEVS (see [Variable structure](variable-structure.md)).

---

## 6. `real_time_thermostat.py`: real time, threads, activities

A thermostat runs paced by the wall clock (`speed=20`: one simulated minute
takes 50 ms). A **sensor thread** posts temperature readings with
`runner.post(...)`. The thermostat switches a heater with hysteresis, and
every five readings it starts an **activity**: a slow moving average computed
in a thread, whose result comes back as input:

```
  t=  4.21 min  {'average': [20.83]}
  t= 12.03 min  {'heater': ['on']}
  t= 22.05 min  {'heater': ['off']}
  ...
30 simulated minutes in 1.50 s of wall time
```

The times vary slightly from run to run because they follow the real clock
(see [Real time](real-time.md)).
