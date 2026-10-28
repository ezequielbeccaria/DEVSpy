import logging

from devspy import Atomic, SimulationManager, Digraph
from devspy.util.logging import FULL, set_level


class Ticker(Atomic):
    def initialize(self):
        self.hold_in("active", 1.0)

    def deltint(self):
        self.hold_in("active", 1.0)


class LoudTicker(Ticker):
    def __init__(self, name):
        super().__init__(name)
        self.shown = 0

    def show_state(self):
        self.shown += 1


def _run(*models):
    g = Digraph("top")
    for m in models:
        g.add(m)
    f = SimulationManager(g)
    f.reset()
    f.simulate_to_time(3.0)


def test_custom_show_state_is_called_with_logging_off():
    loud = LoudTicker("loud")
    _run(loud, Ticker("quiet"))
    assert loud.shown == 4  # once at initialize + once per iteration (t=1,2,3)


def test_default_show_state_logs_when_enabled(caplog):
    set_level(FULL)
    try:
        with caplog.at_level(logging.DEBUG, logger="devspy"):
            _run(Ticker("t"))
    finally:
        set_level(logging.WARNING)
    assert any("Model t's state" in r.getMessage() for r in caplog.records)
    assert any(r.getMessage().startswith("ITERATION 1") for r in caplog.records)
