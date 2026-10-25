"""The 0.3 examples: gym-style stepping, variable structure, real time."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

import autoscaling  # noqa: E402
import gym_loop  # noqa: E402
import real_time_thermostat  # noqa: E402


def test_gym_loop_compares_two_policies_from_one_checkpoint():
    r = gym_loop.run(seed=0, steps=50)
    assert r["time"] == 60.0  # 10 warm-up steps + 50 after the restored checkpoint
    assert r["proportional"] < r["bang-bang"]
    assert r == gym_loop.run(seed=0, steps=50)  # deterministic


def test_autoscaling_grows_and_shrinks_the_server_pool():
    disp = autoscaling.run(seed=1, end=80.0)
    counts = [n for _, n in disp.history]
    assert max(counts) == autoscaling.Dispatcher.MAX_SERVERS  # scaled up in a burst
    assert disp.servers == 1  # and back down after it
    assert disp.created > autoscaling.Dispatcher.MAX_SERVERS  # pool rebuilt for the 2nd burst
    model_names = {c.get_name() for c in disp.get_parent().get_components()}
    assert model_names == {"generator", "dispatcher", *(n for n in model_names if n.startswith("server"))}
    assert sum(n.startswith("server") for n in model_names) == disp.servers


def test_real_time_thermostat_reacts_to_the_sensor_thread():
    outputs = real_time_thermostat.run(minutes=30.0, speed=100.0)
    heater = [v for _, bag in outputs for v in bag.get("heater", ())]
    averages = [v for _, bag in outputs for v in bag.get("average", ())]
    assert heater == ["on", "off"]  # one heating cycle over the oscillation
    assert 4 <= len(averages) <= 6  # one activity every 5 readings
    assert all(18.0 < a < 22.0 for a in averages)
    assert all(0 <= t <= 30.0 for t, _ in outputs)


@pytest.mark.parametrize("module", [gym_loop, autoscaling])
def test_examples_have_a_main(module, capsys):
    import runpy

    runpy.run_path(module.__file__, run_name="__main__")
    assert capsys.readouterr().out
