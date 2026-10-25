"""Three-station manufacturing assembly line — hierarchical DEVS example.

Each `Station` is itself a coupled model containing a `Buffer` and a
`Machine`, so the top-level `Line` is a digraph of digraphs (Coordinator
inside Coordinator). This exercises the nested-coupling paths in the
simulation engine that the flat GPT example does not.

Topology:

    PartGenerator ─▶ Station1 ─▶ Station2 ─▶ Station3 ─▶ Collector

    Station_i:  in ─▶ Buffer ─▶ Machine ─▶ out
                            ◀──next──┘

The bottleneck is the station with the longest service time; metrics
report per-station utilization so it is identified directly.

Run directly:
    python examples/manufacturing_line.py
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from devspy import Atomic, Bag, DevsSuiteFacade, Digraph


@dataclass
class Part:
    id: int
    born_at: float


class PartGenerator(Atomic):
    def __init__(self, interarrival: float) -> None:
        super().__init__("part_gen")
        self.add_outport("out")
        self._iat = interarrival
        self._next_id = 0
        self._clock = 0.0

    def initialize(self) -> None:
        self._next_id = 0
        self._clock = 0.0
        self.hold_in("emit", self._iat)

    def deltint(self) -> None:
        self._clock += self.sigma
        self._next_id += 1
        self.hold_in("emit", self._iat)

    def out(self) -> Bag:
        return {"out": [Part(self._next_id + 1, self._clock + self.sigma)]}


class Buffer(Atomic):
    def __init__(self, name: str = "buffer") -> None:
        super().__init__(name)
        self.add_inport("arrive")
        self.add_inport("next")
        self.add_outport("out")
        self._buffer: deque[Part] = deque()
        self._machine_busy = False
        self._pending: Part | None = None
        self.max_size: int = 0

    def initialize(self) -> None:
        self._buffer.clear()
        self._machine_busy = False
        self._pending = None
        self.max_size = 0
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        # Arrivals first, then the server's "next" signal (fixed, documented order).
        for part in x.get("arrive", ()):
            if not self._machine_busy and self._pending is None:
                self._pending = part
                self._machine_busy = True
            else:
                self._buffer.append(part)
        for _ in x.get("next", ()):
            if self._buffer:
                self._pending = self._buffer.popleft()
            else:
                self._machine_busy = False
        self.max_size = max(self.max_size, len(self._buffer))
        if self._pending is not None:
            self.hold_in("send", 0.0)
        else:
            self.passivate()

    def deltint(self) -> None:
        self._pending = None
        self.passivate()

    def out(self) -> Bag:
        return {"out": [self._pending]} if self._pending is not None else {}


class Machine(Atomic):
    def __init__(self, service_time: float, name: str = "machine") -> None:
        super().__init__(name)
        self.add_inport("in")
        self.add_outport("done")
        self.add_outport("next")
        self._svc = service_time
        self._current: Part | None = None
        self.busy_time: float = 0.0
        self.processed: int = 0

    def initialize(self) -> None:
        self._current = None
        self.busy_time = 0.0
        self.processed = 0
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        if self.phase_is("passive"):
            items = x.get("in")
            if items:
                self._current = items[0]
                self.hold_in("busy", self._svc)
        else:
            self.cont(e)

    def deltint(self) -> None:
        self.busy_time += self.sigma
        self.processed += 1
        self._current = None
        self.passivate()

    def out(self) -> Bag:
        if self._current is None:
            return {}
        return {"done": [self._current], "next": [1]}


class Collector(Atomic):
    def __init__(self) -> None:
        super().__init__("collector")
        self.add_inport("in")
        self.received: list[tuple[float, Part]] = []
        self._clock = 0.0

    def initialize(self) -> None:
        self.received = []
        self._clock = 0.0
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        self._clock += e
        self.received.extend((self._clock, part) for part in x.get("in", ()))


def build_station(name: str, service_time: float) -> tuple[Digraph, Buffer, Machine]:
    buf = Buffer()
    mac = Machine(service_time)
    station = Digraph(name)
    station.add_inport("in")
    station.add_outport("out")
    station.add(buf)
    station.add(mac)
    station.add_coupling(station, "in", buf, "arrive")
    station.add_coupling(buf, "out", mac, "in")
    station.add_coupling(mac, "next", buf, "next")
    station.add_coupling(mac, "done", station, "out")
    return station, buf, mac


@dataclass
class StationRef:
    name: str
    digraph: Digraph
    buffer: Buffer
    machine: Machine


@dataclass
class LineModel:
    line: Digraph
    generator: PartGenerator
    stations: list[StationRef]
    collector: Collector


def build(
    interarrival: float = 1.0,
    service_times: tuple[float, float, float] = (0.8, 1.5, 0.7),
) -> LineModel:
    gen = PartGenerator(interarrival)
    s1, b1, m1 = build_station("station1", service_times[0])
    s2, b2, m2 = build_station("station2", service_times[1])
    s3, b3, m3 = build_station("station3", service_times[2])
    coll = Collector()

    line = Digraph("line")
    line.add(gen)
    line.add(s1)
    line.add(s2)
    line.add(s3)
    line.add(coll)

    line.add_coupling(gen, "out", s1, "in")
    line.add_coupling(s1, "out", s2, "in")
    line.add_coupling(s2, "out", s3, "in")
    line.add_coupling(s3, "out", coll, "in")

    return LineModel(
        line=line,
        generator=gen,
        stations=[
            StationRef("station1", s1, b1, m1),
            StationRef("station2", s2, b2, m2),
            StationRef("station3", s3, b3, m3),
        ],
        collector=coll,
    )


@dataclass
class Result:
    sim_time: float
    parts_generated: int
    parts_completed: int
    throughput: float
    bottleneck: str
    stations: list[dict] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            "Manufacturing line results:",
            f"  sim time            : {self.sim_time}",
            f"  parts generated     : {self.parts_generated}",
            f"  parts completed     : {self.parts_completed}",
            f"  throughput (parts/t): {self.throughput:.4f}",
            f"  bottleneck station  : {self.bottleneck}",
            "  per-station:",
        ]
        for s in self.stations:
            lines.append(
                f"    {s['name']}: util={s['utilization']:.3f}"
                f"  processed={s['processed']}  max_buf={s['max_buffer']}"
            )
        return "\n".join(lines)


def run(
    interarrival: float = 1.0,
    service_times: tuple[float, float, float] = (0.8, 1.5, 0.7),
    end_time: float = 200.0,
) -> Result:
    model = build(interarrival, service_times)
    facade = DevsSuiteFacade(model.line)
    facade.reset()
    facade.simulate_to_time(end_time)

    per_station = []
    for s in model.stations:
        per_station.append(
            {
                "name": s.name,
                "utilization": s.machine.busy_time / end_time,
                "processed": s.machine.processed,
                "max_buffer": s.buffer.max_size,
            }
        )
    bottleneck = max(per_station, key=lambda d: d["utilization"])["name"]
    n_done = len(model.collector.received)

    return Result(
        sim_time=end_time,
        parts_generated=model.generator._next_id,
        parts_completed=n_done,
        throughput=n_done / end_time,
        bottleneck=bottleneck,
        stations=per_station,
    )


if __name__ == "__main__":
    print(run())
