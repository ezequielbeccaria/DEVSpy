from __future__ import annotations

import math

from devspy.simulation.atomic_simulator import AtomicSimulator
from devspy.util.logging import FULL, log

INFINITY = math.inf


class TimeAtomicSimulator(AtomicSimulator):
    """Ports DEVSJAVA facade's `TimeAtomicSimulator`.

    Adds time-limited simulation to the plain `AtomicSimulator`.

    NOTE on faithfulness: the Java `simulate(double time)` uses `i <= time`
    where `i` is the iteration counter. That's preserved in `simulate` to
    match observable behaviour. `simulate_until_time` is the corrected
    companion that gates on `tN <= time`.
    """

    def simulate(self, time: float) -> None:  # type: ignore[override]
        i = 1
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and i <= time:
            log(f"ITERATION {i} ,time: {self.t_n}", FULL)
            self.compute_input_output(self.t_n)
            self.show_output()
            self.delt_func(self.t_n)
            self.show_model_state()
            i += 1
        log(f"Terminated Normally at ITERATION {i} ,time: {self.t_n}", FULL)

    def simulate_from_to(self, init_time: float, end_time: float) -> None:
        self.initialize(init_time)
        self.simulate(end_time)

    def simulate_until_time(self, max_sim_time: float) -> None:
        """Gate on simulated time (not iteration index). Not present in Java."""
        self.t_n = self.next_tn()
        while self.t_n < INFINITY and self.t_n <= max_sim_time:
            self.compute_input_output(self.t_n)
            self.show_output()
            self.delt_func(self.t_n)
            self.show_model_state()
