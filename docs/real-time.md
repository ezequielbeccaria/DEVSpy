# Real time

A real-time run paces the simulation against the wall clock and accepts input
from other threads, for example sensors, sockets or a UI.

```python
runner = f.real_time(speed=1.0)            # simulated time units per wall-clock second
threading.Thread(target=sensor_loop, args=(runner,)).start()
outputs = runner.run(until=600.0, on_output=lambda t, y: actuate(y))
```

- **`run(until, on_output)`** blocks until simulated time `until`, or until
  `stop()`. Simulated time `t` is reached at wall time
  `start + (t - t0) / speed`. Root outputs are returned as `(t, bag)` and also
  passed to `on_output` as they happen. If the host falls behind, overdue
  events run immediately, in order.
- **`post(port, value)`**, **`post({port: [values]})`** and
  **`post(..., to=atomic)`** are thread-safe. The input is delivered at the
  simulated time that matches its arrival, clamped between the last and the
  next event. With `to=`, it goes straight to that atomic's input port.
- **`stop()`** is thread-safe and ends the run.

An input that arrives exactly when an internal event is due is delivered in
its own round right after that event, at the same `t`. The runner cannot know
an input is coming, so it cannot make the two confluent. This is a legal PDEVS
trajectory: the input simply arrives an instant later.

## Activities

Inside a real-time run, an atomic can hand slow work to a thread. Its result
comes back later as external input:

```python
class Worker(Atomic):
    def __init__(self):
        super().__init__("worker")
        self.add_inport("job")
        self.add_inport("activity")     # the result arrives here

    def deltext(self, e, x):
        if "job" in x:
            self.task = self.start_activity(heavy_fn, x["job"][0], port="activity")
        if "activity" in x:
            result = x["activity"][0]
            ...
```

- An exception raised in the activity stops the run and is re-raised by
  `run()`.
- `self.task.cancel()` discards a result that has not been delivered yet. The
  thread itself cannot be interrupted.
- Activities exist only in real time. In logical time, model a known duration
  with `hold_in(phase, duration)`, which is plain DEVS and deterministic.

See `examples/real_time_thermostat.py`.

## Testing real-time code

Pass `clock=` to use a deterministic virtual clock. It must be a `WallClock`
subclass with `now()` and `wait(inbox, timeout)`, where `wait` returns the next
item from `inbox` or `None` after `timeout` seconds. `tests/test_real_time.py`
has a `VirtualClock` that advances instantly and runs scheduled posts.
