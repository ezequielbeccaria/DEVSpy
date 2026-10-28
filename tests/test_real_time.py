"""Real-time runs (paced against a clock) and activities."""

import math
import queue
import threading
import time

import pytest

from devspy import Atomic, SimulationManager, Digraph, WallClock
from tests import reference_pdevs
from tests.test_reference_pdevs import _injections, _multiset, _with_root_input, random_model


class VirtualClock(WallClock):
    """Deterministic clock: waiting advances it; `at(w, fn)` runs `fn` (which
    usually posts) when the clock reaches wall time `w`."""

    def __init__(self):
        self.t = 0.0
        self.schedule = []

    def at(self, wall, fn):
        self.schedule.append((wall, fn))
        self.schedule.sort(key=lambda item: item[0])

    def now(self):
        return self.t

    def wait(self, inbox, timeout):
        try:
            return inbox.get_nowait()
        except queue.Empty:
            pass
        deadline = self.t + timeout
        if self.schedule and self.schedule[0][0] <= deadline:
            wall, fn = self.schedule.pop(0)
            self.t = max(self.t, wall)
            fn()
            try:
                return inbox.get_nowait()
            except queue.Empty:
                return None
        self.t = max(deadline, math.nextafter(self.t, math.inf))
        return None


class Pulse(Atomic):
    def __init__(self, name="pulse", period=1.0):
        super().__init__(name)
        self.add_outport("out")
        self.period = period

    def initialize(self):
        self.k = 0
        self.hold_in("active", self.period)

    def deltint(self):
        self.k += 1
        self.hold_in("active", self.period)

    def out(self):
        return {"out": [self.k]}


class Recorder(Atomic):
    def __init__(self, name="rec"):
        super().__init__(name)
        self.add_inport("in")
        self.add_inport("activity")
        self.add_outport("out")
        self.seen = []

    def initialize(self):
        self.seen = []
        self.passivate()

    def deltext(self, e, x):
        t = self.get_simulator().t_l + e
        for port, values in x.items():
            self.seen.extend((t, port, v) for v in values)
        self.hold_in("reply", 0.0)

    def deltint(self):
        self.passivate()

    def out(self):
        return {"out": [self.seen[-1][2]]}


def _net():
    g = Digraph("g")
    g.add_inport("in")
    g.add_outport("out")
    pulse, rec = Pulse(), Recorder()
    g.add(pulse)
    g.add(rec)
    g.add_coupling(pulse, "out", g, "out")
    g.add_coupling(g, "in", rec, "in")
    g.add_coupling(rec, "out", g, "out")
    return g, pulse, rec


@pytest.mark.parametrize("speed", [1.0, 2.0, 0.5])
def test_events_happen_at_their_wall_time(speed):
    g, _, _ = _net()
    clock = VirtualClock()
    runner = SimulationManager(g).real_time(speed=speed, clock=clock)
    walls = []
    outputs = runner.run(until=3.0, on_output=lambda t, y: walls.append((t, clock.now())))
    assert outputs == [(1.0, {"out": [0]}), (2.0, {"out": [1]}), (3.0, {"out": [2]})]
    assert walls == [(t, t / speed) for t in (1.0, 2.0, 3.0)]


def test_posted_input_arrives_at_the_matching_simulated_time():
    g, _, rec = _net()
    clock = VirtualClock()
    runner = SimulationManager(g).real_time(speed=2.0, clock=clock)
    clock.at(0.75, lambda: runner.post("in", "a"))  # wall 0.75 -> t = 1.5
    outputs = runner.run(until=2.0)
    assert rec.seen == [(1.5, "in", "a")]
    assert outputs == [(1.0, {"out": [0]}), (1.5, {"out": ["a"]}), (2.0, {"out": [1]})]


def test_input_arriving_with_a_due_event_follows_it():
    g, _, rec = _net()
    clock = VirtualClock()
    runner = SimulationManager(g).real_time(clock=clock)
    clock.at(1.0, lambda: runner.post("in", "a"))
    outputs = runner.run(until=1.0)
    assert rec.seen == [(1.0, "in", "a")]
    assert outputs == [(1.0, {"out": [0]}), (1.0, {"out": ["a"]})]


def test_a_late_simulation_catches_up_in_order():
    class Laggy(VirtualClock):
        def wait(self, inbox, timeout):
            item = super().wait(inbox, timeout)
            self.t += 2.5  # the host stalls after every wait
            return item

    g, _, _ = _net()
    runner = SimulationManager(g).real_time(clock=Laggy())
    outputs = runner.run(until=6.0)
    assert [t for t, _ in outputs] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_stop_ends_the_run():
    g, _, _ = _net()
    clock = VirtualClock()
    runner = SimulationManager(g).real_time(clock=clock)
    clock.at(2.5, runner.stop)
    assert [t for t, _ in runner.run()] == [1.0, 2.0]


@pytest.mark.parametrize("seed", range(100))
def test_real_time_run_matches_reference(seed):
    """Posts at the injection times (speed 2: wall = t / 2) give the reference
    trajectory with the runner's policy (an input never joins a due event)."""
    injections = _injections(seed)
    model, log = random_model(seed)
    clock = VirtualClock()
    runner = SimulationManager(_with_root_input(model)).real_time(speed=2.0, clock=clock)
    for t, bag in injections:
        clock.at(t / 2, lambda bag=bag: runner.post(bag))
    outputs = runner.run(until=40.0)

    ref_model, ref_log = random_model(seed)
    ref_outputs = reference_pdevs.run(
        _with_root_input(ref_model), 40.0, injections, confluent_injections=False
    )
    assert log == ref_log
    assert [(t, _multiset(y)) for t, y in outputs] == [(t, _multiset(y)) for t, y in ref_outputs]


# --- with real threads and the real clock -----------------------------------------------
def test_post_from_another_thread():
    g, _, rec = _net()
    runner = SimulationManager(g).real_time(speed=1000.0)  # 1 ms per time unit

    def feeder():
        time.sleep(0.01)
        runner.post("in", "x")

    threading.Thread(target=feeder).start()
    runner.run(until=1e6, on_output=lambda t, y: y["out"] == ["x"] and runner.stop())
    assert [(port, v) for _, port, v in rec.seen] == [("in", "x")]
    assert rec.seen[0][0] > 0


class Worker(Recorder):
    """Starts an activity on its first input; the result comes back on "activity"."""

    def deltext(self, e, x):
        super().deltext(e, x)
        if "in" in x:
            self.job = self.start_activity(lambda v: (time.sleep(0.01), v * 2)[1], x["in"][0])


def test_activity_result_arrives_as_input():
    g = Digraph("g")
    g.add_inport("in")
    g.add_outport("out")
    w = Worker("w")
    g.add(w)
    g.add_coupling(g, "in", w, "in")
    g.add_coupling(w, "out", g, "out")
    f = SimulationManager(g)
    runner = f.real_time(speed=1000.0)
    runner.post("in", 21)
    got = []

    def on_output(t, y):
        got.append(y["out"][0])
        if y["out"][0] == 42:
            runner.stop()

    runner.run(until=1e6, on_output=on_output)
    assert [(port, v) for _, port, v in w.seen] == [("in", 21), ("activity", 42)]
    assert got == [21, 42]
    t_in, t_done = w.seen[0][0], w.seen[1][0]
    assert t_done - t_in >= 9.0  # >= 10 ms of activity at 1000 units/s, minus slack


def test_activity_error_stops_the_run():
    class Failing(Recorder):
        def deltext(self, e, x):
            super().deltext(e, x)
            if "in" in x:
                self.start_activity(lambda: 1 / 0)

    g = Digraph("g")
    g.add_inport("in")
    f_model = Failing("f")
    g.add(f_model)
    g.add_coupling(g, "in", f_model, "in")
    runner = SimulationManager(g).real_time(speed=1000.0)
    runner.post("in", 1)
    with pytest.raises(ZeroDivisionError):
        runner.run(until=1e6)


def test_activities_need_a_real_time_run():
    g = Digraph("g")
    g.add_inport("in")
    w = Worker("w")
    g.add(w)
    g.add_coupling(g, "in", w, "in")
    f = SimulationManager(g)
    with pytest.raises(RuntimeError, match="real-time run"):
        f.inject("in", 1)
