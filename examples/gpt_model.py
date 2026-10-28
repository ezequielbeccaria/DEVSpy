"""Generator → Processor → Transducer (GPT): the canonical DEVS smoke test.

- Generator periodically emits jobs.
- Processor takes `PROCESS_TIME` to complete each job, queues none (drops when busy).
- Transducer observes arrivals and completions; stops itself after OBS_TIME.
"""

from __future__ import annotations

from devspy import Atomic, Bag, SimulationManager, Digraph

GEN_PERIOD = 2.0
PROCESS_TIME = 3.0
OBS_TIME = 20.0


class Generator(Atomic):
    def __init__(self) -> None:
        super().__init__("generator")
        self.add_inport("stop")
        self.add_outport("out")
        self._job_id = 0

    def initialize(self) -> None:
        self._job_id = 0
        self.hold_in("active", GEN_PERIOD)

    def deltint(self) -> None:
        self._job_id += 1
        self.hold_in("active", GEN_PERIOD)

    def deltext(self, e: float, x: Bag) -> None:
        if "stop" in x:
            self.passivate()

    def out(self) -> Bag:
        return {"out": [self._job_id + 1]}


class Processor(Atomic):
    def __init__(self) -> None:
        super().__init__("processor")
        self.add_inport("in")
        self.add_outport("out")
        self._current: int | None = None

    def initialize(self) -> None:
        self._current = None
        self.passivate()

    def deltint(self) -> None:
        self._current = None
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        if self.phase_is("passive"):
            jobs = x.get("in")
            if jobs:
                self._current = jobs[0]
                self.hold_in("busy", PROCESS_TIME)
        else:
            self.cont(e)

    def out(self) -> Bag:
        return {"out": [self._current]} if self._current is not None else {}


class Transducer(Atomic):
    def __init__(self) -> None:
        super().__init__("transducer")
        self.add_inport("arrived")
        self.add_inport("solved")
        self.add_outport("stop")
        self.arrivals: list[tuple[float, int]] = []
        self.completions: list[tuple[float, int]] = []
        self._clock: float = 0.0

    def initialize(self) -> None:
        self.arrivals = []
        self.completions = []
        self._clock = 0.0
        self.hold_in("observing", OBS_TIME)

    def deltint(self) -> None:
        self._clock += self.sigma
        if self.phase_is("observing"):
            self.hold_in("stopping", 0.0)
        else:
            self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        self._clock += e
        self._record(x)
        self.cont(e)

    def deltcon(self, e: float, x: Bag) -> None:
        # Confluent: internal event fires at tN with simultaneous input.
        # Advance the clock by sigma exactly once, then transition and record.
        self._clock += self.sigma
        if self.phase_is("observing"):
            self.hold_in("stopping", 0.0)
        else:
            self.passivate()
        self._record(x)

    def _record(self, x: Bag) -> None:
        self.arrivals.extend((self._clock, job) for job in x.get("arrived", ()))
        self.completions.extend((self._clock, job) for job in x.get("solved", ()))

    def out(self) -> Bag:
        return {"stop": [1]} if self.phase_is("observing") else {}


def build() -> tuple[Digraph, Transducer]:
    gen = Generator()
    proc = Processor()
    trans = Transducer()

    gpt = Digraph("gpt")
    gpt.add(gen)
    gpt.add(proc)
    gpt.add(trans)

    gpt.add_coupling(gen, "out", proc, "in")
    gpt.add_coupling(gen, "out", trans, "arrived")
    gpt.add_coupling(proc, "out", trans, "solved")
    gpt.add_coupling(trans, "stop", gen, "stop")
    return gpt, trans


def run(end_time: float = 30.0) -> Transducer:
    gpt, trans = build()
    manager = SimulationManager(gpt)
    manager.reset()
    manager.simulate_to_time(end_time)
    return trans


def format_trace(trans: Transducer) -> str:
    lines = ["arrivals:"]
    lines.extend(f"  t={t:.4f} job={j}" for t, j in trans.arrivals)
    lines.append("completions:")
    lines.extend(f"  t={t:.4f} job={j}" for t, j in trans.completions)
    return "\n".join(lines)


if __name__ == "__main__":
    trans = run()
    print(format_trace(trans))
