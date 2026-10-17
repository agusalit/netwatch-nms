import csv
import importlib.util
import json
import random
import stat
import time
from pathlib import Path

import pytest

SCENARIO_PATH = Path(__file__).resolve().parent.parent / "testbed" / "scenario.py"


@pytest.fixture()
def scenario():
    spec = importlib.util.spec_from_file_location("testbed_scenario", SCENARIO_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_load_profile_peaks_in_the_evening_and_dips_at_night(scenario):
    assert scenario.load_at(20) > 0.9
    assert scenario.load_at(3) < 0.1
    assert scenario.load_at(23.5) == pytest.approx((scenario.load_at(23) + scenario.load_at(24)) / 2)


def test_planned_events_match_their_scope(scenario):
    rng = random.Random(1)
    kinds = set()
    for i in range(60):
        event = scenario.plan_event(rng, i, now=1000.0, netem_ok=True)
        kinds.add(event.kind)
        assert event.end > event.start
        if event.is_pair_event:
            assert ">" in event.target and "rate_multiplier" in event.params
        else:
            assert event.target in scenario.NODES
    assert kinds == set(scenario.ANOMALY_KINDS)


def test_netem_events_are_never_planned_when_the_kernel_lacks_netem(scenario):
    rng = random.Random(2)
    for i in range(60):
        assert scenario.plan_event(rng, i, now=0.0, netem_ok=False).is_pair_event


def test_only_the_targeted_pair_is_affected(scenario):
    event = scenario.Event(1, "flood", "nw-node1>node2", 0, 10, {"rate_multiplier": 8.0})
    assert scenario.pair_multiplier(event, "nw-node1", "node2") == 8.0
    assert scenario.pair_multiplier(event, "nw-node2", "node3") == 1.0
    assert scenario.pair_multiplier(None, "nw-node1", "node2") == 1.0


def test_run_writes_a_ground_truth_file_with_a_closed_event(scenario, tmp_path):
    """Full loop against a fake `docker` that only records calls."""
    calls = tmp_path / "calls.log"
    fake = tmp_path / "docker"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {calls}\n'
        'case "$1" in inspect) echo true;; esac\n'
        'case "$*" in *iperf3*) sleep 1;; esac\n'
        "exit 0\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)

    scenario.DOCKER = str(fake)
    scenario.ANOMALY_KINDS = {"flood": ("pair", (0.02, 0.03), 1)}
    args = scenario.parse_args([
        "--hours", "0.002", "--cycle", "1", "--first-anomaly-after", "0.02",
        "--seed", "3", "--output-dir", str(tmp_path / "runs"), "--day-minutes", "60", "--start-hour", "19",
    ])
    scenario.run(args)

    run_dir = next((tmp_path / "runs").iterdir())
    rows = list(csv.DictReader(open(run_dir / "ground_truth.csv")))
    assert rows, "expected at least one completed anomaly"
    assert rows[0]["kind"] == "flood" and rows[0]["end_utc"] > rows[0]["start_utc"]
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["seed"] == 3
    assert "iperf3" in calls.read_text()
