"""Real time: a thermostat paced by the wall clock, fed by a sensor thread.

A sensor thread posts temperature readings with `runner.post(...)` while the
simulation runs. The thermostat switches the heater with hysteresis, and every
few readings it starts an *activity*: a computation in a thread (here a slow
moving average) whose result comes back to the model as input. With `speed=20`
one simulated minute takes 50 ms of wall time.
"""

from __future__ import annotations

import math
import threading
import time

from devspy import Atomic, Bag, SimulationManager, Digraph


def slow_average(readings: list[float]) -> float:
    time.sleep(0.01)  # stands in for real work (a model, a database query...)
    return sum(readings) / len(readings)


class Thermostat(Atomic):
    LOW, HIGH = 19.0, 21.0

    def __init__(self) -> None:
        super().__init__("thermostat")
        self.add_inport("temp")
        self.add_inport("activity")
        self.add_outport("heater")
        self.add_outport("average")

    def initialize(self) -> None:
        self.heating = False
        self.readings: list[float] = []
        self.emit: Bag = {}
        self.passivate()

    def deltext(self, e: float, x: Bag) -> None:
        self.emit = {}
        for temp in x.get("temp", ()):
            self.readings.append(temp)
            if temp < self.LOW and not self.heating:
                self.heating = True
                self.emit["heater"] = ["on"]
            elif temp > self.HIGH and self.heating:
                self.heating = False
                self.emit["heater"] = ["off"]
            if len(self.readings) % 5 == 0:
                self.start_activity(slow_average, self.readings[-5:])
        for avg in x.get("activity", ()):
            self.emit["average"] = [round(avg, 2)]
        if self.emit:
            self.hold_in("reporting", 0.0)
        else:
            self.passivate()

    def deltint(self) -> None:
        self.emit = {}
        self.passivate()

    def out(self) -> Bag:
        return self.emit


def build() -> Digraph:
    g = Digraph("home")
    g.add_inport("temp")
    g.add_outport("heater")
    g.add_outport("average")
    thermo = Thermostat()
    g.add(thermo)
    g.add_coupling(g, "temp", thermo, "temp")
    g.add_coupling(thermo, "heater", g, "heater")
    g.add_coupling(thermo, "average", g, "average")
    return g


def run(minutes: float = 30.0, speed: float = 20.0) -> list[tuple[float, Bag]]:
    """Simulate `minutes` (simulated time unit: 1 minute) in real time."""
    runner = SimulationManager(build()).real_time(speed=speed)

    def sensor() -> None:
        # One reading per simulated minute: a slow oscillation around 20 °C.
        for minute in range(int(minutes)):
            runner.post("temp", round(20.0 + 1.5 * math.sin(minute / 3.0), 2))
            time.sleep(1.0 / speed)

    threading.Thread(target=sensor, daemon=True).start()
    return runner.run(until=minutes)


if __name__ == "__main__":
    start = time.perf_counter()
    outputs = run()
    wall = time.perf_counter() - start
    for t, bag in outputs:
        print(f"  t={t:6.2f} min  {bag}")
    print(f"30 simulated minutes in {wall:.2f} s of wall time")
