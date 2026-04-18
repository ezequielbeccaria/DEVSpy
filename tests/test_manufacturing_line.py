"""Tests for the hierarchical manufacturing line example.

Validates nested-digraph routing (Coordinator inside Coordinator) by checking
that parts flow end-to-end and per-station metrics make physical sense.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from manufacturing_line import run  # noqa: E402


def test_parts_flow_end_to_end():
    r = run(interarrival=1.0, service_times=(0.8, 1.5, 0.7), end_time=100.0)
    # Some parts must have made it through all three stations.
    assert r.parts_completed > 0
    # Conservation: completed cannot exceed generated.
    assert r.parts_completed <= r.parts_generated


def test_bottleneck_is_slowest_station():
    """Station with the longest service time should saturate first."""
    r = run(interarrival=1.0, service_times=(0.8, 1.5, 0.7), end_time=200.0)
    assert r.bottleneck == "station2"
    util2 = next(s for s in r.stations if s["name"] == "station2")["utilization"]
    assert util2 > 0.9


def test_bottleneck_moves_with_service_times():
    """Make station3 the slowest — it should now be the bottleneck."""
    r = run(interarrival=1.0, service_times=(0.5, 0.6, 1.4), end_time=200.0)
    assert r.bottleneck == "station3"


def test_throughput_bounded_by_bottleneck():
    """Long-run throughput cannot exceed 1 / max(service_times)."""
    svc = (0.8, 1.5, 0.7)
    r = run(interarrival=1.0, service_times=svc, end_time=500.0)
    bottleneck_rate = 1.0 / max(svc)
    assert r.throughput <= bottleneck_rate * 1.05  # tiny overshoot ok


def test_underloaded_line_keeps_up():
    """Slow generator vs fast machines: throughput tracks arrival rate."""
    arrival_rate = 1.0 / 5.0  # one part every 5 time units
    r = run(interarrival=5.0, service_times=(0.5, 0.5, 0.5), end_time=200.0)
    assert r.throughput == pytest.approx(arrival_rate, rel=0.10)
    for s in r.stations:
        assert s["utilization"] < 0.20
