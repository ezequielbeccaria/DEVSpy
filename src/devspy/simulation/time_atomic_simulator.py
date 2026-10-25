from __future__ import annotations

import math

from devspy.simulation.atomic_simulator import AtomicSimulator

INFINITY = math.inf


class TimeAtomicSimulator(AtomicSimulator):
    """Adds time-limited simulation to the plain `AtomicSimulator`.

    `simulate(time)` runs every event with `t_n <= time`. (DEVSJAVA's version
    compared the *iteration counter* with `time`; DEVSpy < 0.3 copied that.)
    """

    def simulate(self, time: float) -> None:  # type: ignore[override]
        self._run(INFINITY, time)

    def simulate_from_to(self, init_time: float, end_time: float) -> None:
        self.initialize(init_time)
        self.simulate(end_time)

    def simulate_until_time(self, max_sim_time: float) -> None:
        """Alias of `simulate(max_sim_time)`, kept for compatibility."""
        self.simulate(max_sim_time)
