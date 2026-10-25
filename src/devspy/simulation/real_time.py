"""Real-time execution: simulated time paced by a wall clock, with external input
and activity results arriving from other threads."""

from __future__ import annotations

import math
import queue
import threading
import time
from typing import Any, Callable, Optional

from devspy.modeling.devs import Bag


class WallClock:
    """The clock a `RealTimeRunner` paces against. Tests substitute a virtual one."""

    def now(self) -> float:
        return time.monotonic()

    def wait(self, inbox: "queue.Queue", timeout: float) -> Any:
        """Block until an item arrives in `inbox` (returned) or `timeout`
        seconds pass (returns None)."""
        try:
            return inbox.get(timeout=max(timeout, 0.0))
        except queue.Empty:
            return None


class _Stop:
    pass


class RealTimeRunner:
    """Runs a simulator so that simulated time t is reached at wall time
    `start + (t - t0) / speed`.

    `post()` and `stop()` are the only methods meant to be called from other
    threads. An input is delivered at the simulated time that corresponds to its
    arrival, clamped between the last and the next event. Every event due by
    then runs first, so an input that arrives exactly when an internal event is
    due is delivered in a separate round after it, at the same t. (The runner
    cannot know an input is coming, so it cannot make the two confluent.) If
    the simulation falls behind the clock, due events run immediately, one
    after another.
    """

    def __init__(self, sim: Any, speed: float = 1.0, clock: Optional[WallClock] = None) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.sim = sim
        self.speed = speed
        self.clock = clock or WallClock()
        self._inbox: queue.Queue = queue.Queue()
        self._pending: list = []

    # --- thread-safe -------------------------------------------------------
    def post(self, port_or_bag: str | Bag, value: Any = None, *, to: Any = None) -> None:
        """Deliver external input as soon as possible: on a root input port, or on
        an input port of the atomic model `to`. Safe to call from any thread."""
        bag = port_or_bag if isinstance(port_or_bag, dict) else {str(port_or_bag): [value]}
        self._inbox.put((to, bag))

    def stop(self) -> None:
        """Make `run()` return as soon as possible. Safe to call from any thread."""
        self._inbox.put(_Stop())

    # --- the loop ----------------------------------------------------------
    def run(
        self, until: float = math.inf, on_output: Optional[Callable[[float, Bag], None]] = None
    ) -> list[tuple[float, Bag]]:
        """Run in real time until simulated time `until` (or `stop()`); return the
        root outputs as `(t, bag)`, also passing each to `on_output` as it happens."""
        sim = self.sim
        if not sim.initialized:
            sim.initialize(0.0)
        outputs: list[tuple[float, Bag]] = []
        sink = _Sink(outputs, on_output)
        saved = sim._sink, sim._stop_on_output, getattr(sim, "_rt_runner", None)
        sim._sink, sim._stop_on_output, sim._rt_runner = sink, False, self
        t0, wall0 = sim.t_l, self.clock.now()
        try:
            while True:
                now_t = t0 + (self.clock.now() - wall0) * self.speed
                t_next = sim.next_tn()
                horizon = min(t_next, until)
                timeout = 3600.0 if horizon == math.inf else (horizon - now_t) / self.speed
                if t_next <= until and timeout <= 0:
                    sim._run(1, t_next)  # due (or overdue): run it now
                    continue
                if self._pending:
                    item = self._pending.pop(0)
                elif timeout <= 0:  # t_next > until and the clock reached until
                    return outputs
                else:
                    item = self.clock.wait(self._inbox, timeout)
                if item is None:
                    continue
                if isinstance(item, _Stop):
                    return outputs
                now_t = t0 + (self.clock.now() - wall0) * self.speed
                if sim.next_tn() <= min(now_t, until):
                    self._pending.insert(0, item)  # run what is due first
                    continue
                self._deliver(item, max(min(now_t, sim.next_tn(), until), sim.t_l))
        finally:
            sim._sink, sim._stop_on_output, sim._rt_runner = saved

    def _deliver(self, item, t: float) -> None:
        to, bag = item
        if isinstance(bag, _Failure):
            raise bag.error
        if to is None:
            self.sim.inject_at(t, bag)
        else:
            self.sim.inject_to(to, t, bag)


class _Sink(list):
    """A root-output sink that also forwards each output to a callback."""

    def __init__(self, target: list, callback) -> None:
        super().__init__()
        self.target = target
        self.callback = callback

    def append(self, item) -> None:
        self.target.append(item)
        if self.callback is not None:
            self.callback(*item)


class _Failure:
    def __init__(self, error: BaseException) -> None:
        self.error = error


class Activity:
    """A computation running in a thread on behalf of an atomic model, during a
    real-time run. Its result arrives at the model as external input on `port`
    (as DEVSJAVA's `outputFromActivity`). An exception in it stops the run."""

    def __init__(self, runner: RealTimeRunner, model: Any, port: str, fn, args, kwargs):
        self._runner = runner
        self._model = model
        self._port = port
        self._cancelled = threading.Event()
        self._thread = threading.Thread(
            target=self._main, args=(fn, args, kwargs), daemon=True,
            name=f"activity-{model.get_name()}",
        )
        self._thread.start()

    def _main(self, fn, args, kwargs) -> None:
        try:
            result = fn(*args, **kwargs)
        except BaseException as error:  # surfaced in the runner's thread
            self._runner._inbox.put((self._model, _Failure(error)))
            return
        if not self._cancelled.is_set():
            self._runner.post(self._port, result, to=self._model)

    def cancel(self) -> None:
        """Discard the result if it has not been delivered yet. (The thread itself
        cannot be interrupted; it runs to completion.)"""
        self._cancelled.set()

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout)
