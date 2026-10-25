"""Watchdog pattern: a broadcaster pings N watchdogs every `period`; each ping
restarts the watchdog's timeout (t_n moves later on every input). Each restart
leaves a stale heap entry behind; they only drain once time passes them.

usage: python timeout_model.py N PERIOD TIMEOUT END
"""
import resource
import sys
import time

from devspy import Atomic, DevsSuiteFacade, Digraph


class Broadcaster(Atomic):
    def __init__(self, period):
        super().__init__("bcast")
        self.add_outport("out")
        self.period = period

    def initialize(self):
        self.hold_in("active", self.period)

    def deltint(self):
        self.hold_in("active", self.period)

    def out(self):
        return {"out": [1]}


class Watchdog(Atomic):
    def __init__(self, name, timeout):
        super().__init__(name)
        self.add_inport("in")
        self.timeout = timeout

    def initialize(self):
        self.fired = 0
        self.hold_in("waiting", self.timeout)

    def deltext(self, e, x):
        self.hold_in("waiting", self.timeout)

    def deltint(self):
        self.fired += 1
        self.hold_in("waiting", self.timeout)


def build(n, period, timeout):
    g = Digraph("watch")
    b = Broadcaster(period)
    g.add(b)
    for i in range(n):
        w = Watchdog(f"w{i}", timeout)
        g.add(w)
        g.add_coupling(b, "out", w, "in")
    return g


if __name__ == "__main__":
    n, period, timeout, end = int(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
    f = DevsSuiteFacade(build(n, period, timeout))
    f.reset()
    t0 = time.perf_counter()
    f.simulate_to_time(end)
    dt = (time.perf_counter() - t0) * 1e3
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"n={n} wall={dt:.0f}ms heap={len(f.get_simulator()._heap)} maxrss={rss}MiB")
