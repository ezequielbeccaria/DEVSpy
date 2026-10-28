"""Variable structure: a dispatcher that adds and removes servers at run time.

Jobs arrive in bursts. The dispatcher keeps a queue; when it grows past a
threshold the dispatcher adds a `Server` model to its parent digraph and couples
it (`add_model`, `add_coupling`), and when a server has been idle for a while it
removes it (`remove_model`). Changes made inside a transition take effect after
the current round, as in DSDEVS.
"""

from __future__ import annotations

import random

from devspy import Atomic, Bag, SimulationManager, Digraph


class Generator(Atomic):
    """Bursty arrivals: fast for 20 time units, slow for the next 20, and so on."""

    def __init__(self, seed: int) -> None:
        super().__init__("generator")
        self.add_outport("job")
        self.seed = seed

    def initialize(self) -> None:
        self.rng = random.Random(self.seed)
        self.clock = 0.0
        self.n = 0
        self.hold_in("active", self._gap())

    def _gap(self) -> float:
        rate = 3.0 if int(self.clock // 20) % 2 == 0 else 0.3
        return self.rng.expovariate(rate)

    def deltint(self) -> None:
        self.clock += self.sigma
        self.n += 1
        self.hold_in("active", self._gap())

    def out(self) -> Bag:
        return {"job": [self.n]}


class Server(Atomic):
    """Serves one job at a time. Assignments are broadcast to every server as
    {server name: job}; each server takes only the job addressed to it."""

    def __init__(self, name: str, service: float) -> None:
        super().__init__(name)
        self.add_inport("job")
        self.add_outport("done")
        self.service = service

    def initialize(self) -> None:
        self.job = None
        self.passivate_in("idle")

    def deltext(self, e: float, x: Bag) -> None:
        for assignment in x["job"]:
            if self.name in assignment:
                self.job = assignment[self.name]
                self.hold_in("busy", self.service)
                return
        self.cont(e)  # not for us

    def deltint(self) -> None:
        self.passivate_in("idle")

    def out(self) -> Bag:
        return {"done": [self.name]}


class Dispatcher(Atomic):
    """Sends queued jobs to idle servers; scales the server pool up and down."""

    SCALE_UP_QUEUE = 4
    IDLE_LIMIT = 5.0
    MAX_SERVERS = 6

    def __init__(self) -> None:
        super().__init__("dispatcher")
        self.add_inport("job")
        self.add_inport("done")
        self.add_outport("assign")
        self.history: list[tuple[float, int]] = []

    def initialize(self) -> None:
        self.clock = 0.0
        self.queue: list[int] = []
        self.idle: dict[str, float] = {}  # server name -> idle since
        self.servers = 0
        self.created = 0
        self.history = []
        self.pending: dict[str, int] = {}
        self._add_server()
        self.passivate()

    # --- structure changes ------------------------------------------------
    def _add_server(self) -> None:
        name = f"server{self.created}"
        self.created += 1
        self.servers += 1
        self.add_model(Server(name, service=1.0))
        self.add_coupling(self, "assign", name, "job")
        self.add_coupling(name, "done", self, "done")
        self.idle[name] = self.clock

    def _remove_server(self, name: str) -> None:
        self.remove_model(name)
        del self.idle[name]
        self.servers -= 1

    # --- DEVS -------------------------------------------------------------
    def deltext(self, e: float, x: Bag) -> None:
        self.clock += e
        self.queue.extend(x.get("job", ()))
        for name in x.get("done", ()):
            self.idle[name] = self.clock
        self._plan()

    def deltint(self) -> None:
        self.clock += self.sigma
        self.pending = {}
        self._plan()

    def _plan(self) -> None:
        if len(self.queue) > self.SCALE_UP_QUEUE and self.servers < self.MAX_SERVERS:
            self._add_server()
        for name, since in list(self.idle.items()):
            if self.servers > 1 and not self.queue and self.clock - since > self.IDLE_LIMIT:
                self._remove_server(name)
        self.history.append((round(self.clock, 3), self.servers))
        # One queued job per idle server, emitted after a zero-time hold.
        self.pending = {}
        for name in sorted(self.idle):
            if not self.queue:
                break
            self.pending[name] = self.queue.pop(0)
            del self.idle[name]
        if self.pending:
            self.hold_in("assigning", 0.0)
        else:
            self.passivate()

    def out(self) -> Bag:
        return {"assign": [self.pending]} if self.pending else {}


def build(seed: int = 1) -> tuple[Digraph, Dispatcher]:
    g = Digraph("farm")
    gen, disp = Generator(seed), Dispatcher()
    g.add(gen)
    g.add(disp)
    g.add_coupling(gen, "job", disp, "job")
    return g, disp


def run(seed: int = 1, end: float = 80.0) -> Dispatcher:
    g, disp = build(seed)
    SimulationManager(g).advance(end)
    return disp


if __name__ == "__main__":
    disp = run()
    peak = max(n for _, n in disp.history)
    print(f"servers created: {disp.created}, peak pool: {peak}, final pool: {disp.servers}")
    last = None
    for t, n in disp.history:
        if n != last:
            print(f"  t={t:7.3f}  servers={n}")
            last = n
