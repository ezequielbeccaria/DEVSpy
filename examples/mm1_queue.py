"""M/M/1 queueing system simulated as a coupled DEVS model.

Components:
    Generator  - Poisson arrivals (rate `lam`).
    Queue      - FIFO buffer; dispatches to Server when free.
    Server     - exponential service (rate `mu`); signals Queue for next job.
    Statistics - records arrivals/departures and computes Little's-Law metrics.

Run directly:
    python examples/mm1_queue.py
"""

from __future__ import annotations

import random
import statistics as pystats
from collections import deque
from dataclasses import dataclass

from devspy import Atomic, Content, DevsSuiteFacade, Digraph, IntEnt, Message


@dataclass
class Job:
    id: int


class Generator(Atomic):
    def __init__(self, lam: float, rng: random.Random) -> None:
        super().__init__("generator")
        self.add_outport("out")
        self._lam = lam
        self._rng = rng
        self._next_id = 0

    def initialize(self) -> None:
        self._next_id = 0
        self.hold_in("active", self._rng.expovariate(self._lam))

    def deltint(self) -> None:
        self._next_id += 1
        self.hold_in("active", self._rng.expovariate(self._lam))

    def out(self) -> Message:
        m = Message()
        m.add(Content("out", Job(self._next_id + 1)))
        return m


class Queue(Atomic):
    def __init__(self) -> None:
        super().__init__("queue")
        self.add_inport("arrive")
        self.add_inport("next")
        self.add_outport("out")
        self._buffer: deque[Job] = deque()
        self._server_busy = False
        self._pending: Job | None = None
        self.max_size: int = 0

    def initialize(self) -> None:
        self._buffer.clear()
        self._server_busy = False
        self._pending = None
        self.max_size = 0
        self.passivate()

    def deltext(self, e: float, x: Message) -> None:
        for c in x:
            port = c.get_port_name()
            if port == "arrive":
                job = c.get_value()
                if not self._server_busy and self._pending is None:
                    self._pending = job
                    self._server_busy = True
                else:
                    self._buffer.append(job)
            elif port == "next":
                if self._buffer:
                    self._pending = self._buffer.popleft()
                else:
                    self._server_busy = False
        self.max_size = max(self.max_size, len(self._buffer))
        if self._pending is not None:
            self.hold_in("send", 0.0)
        else:
            self.passivate()

    def deltint(self) -> None:
        self._pending = None
        self.passivate()

    def out(self) -> Message:
        m = Message()
        if self._pending is not None:
            m.add(Content("out", self._pending))
        return m


class Server(Atomic):
    def __init__(self, mu: float, rng: random.Random) -> None:
        super().__init__("server")
        self.add_inport("in")
        self.add_outport("done")
        self.add_outport("next")
        self._mu = mu
        self._rng = rng
        self._current: Job | None = None
        self.busy_time: float = 0.0

    def initialize(self) -> None:
        self._current = None
        self.busy_time = 0.0
        self.passivate()

    def deltext(self, e: float, x: Message) -> None:
        if self.phase_is("passive"):
            for c in x:
                if c.get_port_name() == "in":
                    self._current = c.get_value()
                    self.hold_in("busy", self._rng.expovariate(self._mu))
                    return
        else:
            self.cont(e)

    def deltint(self) -> None:
        self.busy_time += self.sigma
        self._current = None
        self.passivate()

    def out(self) -> Message:
        m = Message()
        if self._current is not None:
            m.add(Content("done", self._current))
            m.add(Content("next", IntEnt(1)))
        return m


class Statistics(Atomic):
    def __init__(self) -> None:
        super().__init__("stats")
        self.add_inport("arrival")
        self.add_inport("departure")
        self.arrivals: list[tuple[float, int]] = []
        self.departures: list[tuple[float, int]] = []
        self._clock: float = 0.0

    def initialize(self) -> None:
        self.arrivals = []
        self.departures = []
        self._clock = 0.0
        self.passivate()

    def deltext(self, e: float, x: Message) -> None:
        self._clock += e
        for c in x:
            port = c.get_port_name()
            if port == "arrival":
                self.arrivals.append((self._clock, c.get_value().id))
            elif port == "departure":
                self.departures.append((self._clock, c.get_value().id))


@dataclass
class Result:
    lam: float
    mu: float
    sim_time: float
    n_arrivals: int
    n_departures: int
    rho_theoretical: float
    utilization: float
    mean_wait: float
    mean_queue_length: float

    def __str__(self) -> str:
        return (
            f"M/M/1 results (lambda={self.lam}, mu={self.mu}, t={self.sim_time}):\n"
            f"  arrivals      : {self.n_arrivals}\n"
            f"  departures    : {self.n_departures}\n"
            f"  rho (theory)  : {self.rho_theoretical:.4f}\n"
            f"  utilization   : {self.utilization:.4f}\n"
            f"  mean wait W   : {self.mean_wait:.4f}\n"
            f"  mean L = lam*W: {self.mean_queue_length:.4f}"
        )


def build(
    lam: float, mu: float, seed: int
) -> tuple[Digraph, Generator, Queue, Server, Statistics]:
    rng = random.Random(seed)
    gen = Generator(lam, rng)
    q = Queue()
    srv = Server(mu, rng)
    stats = Statistics()

    mm1 = Digraph("mm1")
    mm1.add(gen)
    mm1.add(q)
    mm1.add(srv)
    mm1.add(stats)

    mm1.add_coupling(gen, "out", q, "arrive")
    mm1.add_coupling(gen, "out", stats, "arrival")
    mm1.add_coupling(q, "out", srv, "in")
    mm1.add_coupling(srv, "next", q, "next")
    mm1.add_coupling(srv, "done", stats, "departure")
    return mm1, gen, q, srv, stats


def run(lam: float = 1.0, mu: float = 1.5, seed: int = 42, end_time: float = 1000.0) -> Result:
    mm1, _gen, _q, srv, stats = build(lam, mu, seed)
    facade = DevsSuiteFacade(mm1)
    facade.reset()
    facade.simulate_to_time(end_time)

    by_id = {jid: t for t, jid in stats.arrivals}
    waits = [
        dep_t - by_id[jid] for dep_t, jid in stats.departures if jid in by_id
    ]
    mean_wait = pystats.fmean(waits) if waits else 0.0

    return Result(
        lam=lam,
        mu=mu,
        sim_time=end_time,
        n_arrivals=len(stats.arrivals),
        n_departures=len(stats.departures),
        rho_theoretical=lam / mu,
        utilization=srv.busy_time / end_time,
        mean_wait=mean_wait,
        mean_queue_length=lam * mean_wait,
    )


if __name__ == "__main__":
    print(run())
