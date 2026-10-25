from __future__ import annotations

import math

from devspy.modeling.digraph import Digraph
from devspy.simulation.coordinator import Coordinator
from devspy.util.logging import FULL, is_enabled, log

INFINITY = math.inf


class TimeCoordinator(Coordinator):
    """Ports DEVSJAVA facade's `TimeCoordinator`.

    Adds `simulate(max_sim_time)` that gates on simulated time
    (`t_n <= max_sim_time`), plus `stop_simulation()`.
    """

    def __init__(self, coupled: Digraph, set_simulators: bool = True) -> None:
        super().__init__(coupled, set_simulators=set_simulators)
        self._stop_sim_flag = False

    def simulate(self, max_sim_time: float) -> None:  # type: ignore[override]
        self._stop_sim_flag = False
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and self.t_n <= max_sim_time and not self._stop_sim_flag:
            if is_enabled(FULL):
                log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.wrap_deltfunc(self.t_n)
            self.show_model_state()
            i += 1

    def simulate_from_to(self, init_time: float, max_sim_time: float) -> None:
        self.initialize(init_time)
        self.simulate(max_sim_time)

    def stop_simulation(self) -> None:
        self._stop_sim_flag = True
