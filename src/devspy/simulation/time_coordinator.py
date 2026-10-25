from __future__ import annotations

import math

from devspy.simulation.coordinator import Coordinator

INFINITY = math.inf


class TimeCoordinator(Coordinator):
    """Adds `simulate(max_sim_time)`, which runs every round with
    `t_n <= max_sim_time` (`stop_simulation()` ends it early)."""

    def simulate(self, max_sim_time: float) -> None:  # type: ignore[override]
        self._run(INFINITY, max_sim_time)

    def simulate_from_to(self, init_time: float, max_sim_time: float) -> None:
        self.initialize(init_time)
        self.simulate(max_sim_time)
