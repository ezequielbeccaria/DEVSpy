"""Smoke + sanity tests for the M/M/1 queue example."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from mm1_queue import run  # noqa: E402


def test_no_jobs_lost():
    r = run(lam=1.0, mu=1.5, seed=42, end_time=200.0)
    # Every arrival eventually departs or is still in the system at end.
    residual = r.n_arrivals - r.n_departures
    assert residual >= 0
    assert residual <= 5  # bounded steady-state queue residual


def test_utilization_within_tolerance():
    """Observed utilization should converge toward rho = lam/mu."""
    r = run(lam=1.0, mu=1.5, seed=42, end_time=2000.0)
    assert r.rho_theoretical == pytest.approx(0.6667, abs=1e-3)
    assert r.utilization == pytest.approx(r.rho_theoretical, abs=0.05)


def test_mean_wait_close_to_theory():
    """For M/M/1 the mean sojourn time W = 1/(mu - lam)."""
    lam, mu = 1.0, 1.5
    r = run(lam=lam, mu=mu, seed=42, end_time=2000.0)
    theoretical_w = 1.0 / (mu - lam)
    assert r.mean_wait == pytest.approx(theoretical_w, rel=0.20)


def test_low_load_low_utilization():
    """At low rho the server is mostly idle."""
    r = run(lam=1.0, mu=10.0, seed=11, end_time=500.0)
    assert r.utilization < 0.2
    assert r.mean_wait < 0.25
