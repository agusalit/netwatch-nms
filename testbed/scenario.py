#!/usr/bin/env python3
"""
Drives the SNMP testbed: generates real traffic between the three nodes on a
hotel-like daily pattern and injects labelled anomalies, writing every
anomaly's exact start and end (UTC) to a ground-truth CSV. Nothing here fakes
counter values - the nodes' snmpd reports what the traffic really did.

Runs on the host (needs the docker CLI and `docker compose up -d` in testbed/):
    python testbed/scenario.py                       # real-time day, until Ctrl+C
    python testbed/scenario.py --day-minutes 120     # one "day" compressed into 2 h
    python testbed/scenario.py --no-anomalies        # normal-behaviour data only
    python testbed/scenario.py --hours 6 --seed 42   # reproducible 6 h run

Output: testbed/runs/<UTC timestamp>/ground_truth.csv and meta.json
Standard library only.
"""
import argparse
import csv
import json
import os
import random
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DOCKER = os.getenv("DOCKER_BIN", "docker")

# (client container, DNS name of the server on the compose network). A ring, so
# every iperf3 server serves exactly one client at a time.
RING = [("nw-node1", "node2"), ("nw-node2", "node3"), ("nw-node3", "node1")]
NODES = ["nw-node1", "nw-node2", "nw-node3"]
NETEM_IFACE = "eth0"

# Relative load by hour of day (0..23): quiet nights, a morning bump around
# check-out, and an evening peak - the pattern a static threshold struggles with.
HOURLY_PROFILE = [
    0.10, 0.08, 0.07, 0.07, 0.08, 0.12,
    0.25, 0.45, 0.55, 0.50, 0.45, 0.50,
    0.55, 0.50, 0.45, 0.50, 0.60, 0.75,
    0.90, 1.00, 1.00, 0.95, 0.60, 0.25,
]

# kind -> (applies to, duration range in minutes, weight)
ANOMALY_KINDS = {
    "flood": ("pair", (2, 5), 3),
    "silence": ("pair", (3, 6), 2),
    "sustained_high": ("pair", (8, 15), 2),
    "packet_loss": ("node", (3, 6), 2),
    "latency": ("node", (3, 6), 2),
}
RATE_MULTIPLIER = {"flood": 8.0, "silence": 0.0, "sustained_high": 3.0}


def load_at(hour: float) -> float:
    """Relative load at a fractional hour of day, linearly interpolated."""
    hour %= 24
    lower = int(hour)
    frac = hour - lower
    return HOURLY_PROFILE[lower] * (1 - frac) + HOURLY_PROFILE[(lower + 1) % 24] * frac


def utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Event:
    event_id: int
    kind: str
    target: str            # "nw-node1>node2" for pairs, "nw-node2" for nodes
    start: float
    end: float
    params: dict = field(default_factory=dict)
    interrupted: bool = False

    @property
    def is_pair_event(self):
        return self.kind in RATE_MULTIPLIER


def plan_event(rng: random.Random, event_id: int, now: float, netem_ok: bool) -> Event:
    kinds = [k for k in ANOMALY_KINDS if netem_ok or k in RATE_MULTIPLIER]
    kind = rng.choices(kinds, weights=[ANOMALY_KINDS[k][2] for k in kinds])[0]
    scope, (lo, hi), _ = ANOMALY_KINDS[kind]
    duration = rng.uniform(lo, hi) * 60
    params = {}
    if scope == "pair":
        client, server = rng.choice(RING)
        target = f"{client}>{server}"
        params["rate_multiplier"] = RATE_MULTIPLIER[kind]
    else:
        target = rng.choice(NODES)
        if kind == "packet_loss":
            params["loss_percent"] = rng.choice([20, 30, 40])
        else:
            params["delay_ms"] = rng.choice([150, 250, 400])
    return Event(event_id, kind, target, now, now + duration, params)


def pair_multiplier(event, client: str, server: str) -> float:
    if event and event.is_pair_event and event.target == f"{client}>{server}":
        return RATE_MULTIPLIER[event.kind]
    return 1.0


def docker(*args, check=False):
    return subprocess.run([DOCKER, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=check)


def netem_supported() -> bool:
    ok = docker("exec", NODES[0], "tc", "qdisc", "replace", "dev", NETEM_IFACE, "root", "netem", "delay", "0ms").returncode == 0
    docker("exec", NODES[0], "tc", "qdisc", "del", "dev", NETEM_IFACE, "root")
    return ok


def apply_netem(event: Event):
    spec = (["loss", f"{event.params['loss_percent']}%"] if event.kind == "packet_loss"
            else ["delay", f"{event.params['delay_ms']}ms", f"{event.params['delay_ms'] // 4}ms"])
    docker("exec", event.target, "tc", "qdisc", "replace", "dev", NETEM_IFACE, "root", "netem", *spec)


def clear_netem(node: str):
    docker("exec", node, "tc", "qdisc", "del", "dev", NETEM_IFACE, "root")


def containers_running() -> bool:
    for name in NODES:
        result = subprocess.run([DOCKER, "inspect", "-f", "{{.State.Running}}", name],
                                capture_output=True, text=True)
        if result.returncode != 0 or result.stdout.strip() != "true":
            return False
    return True


class GroundTruth:
    HEADER = ["event_id", "kind", "target", "start_utc", "end_utc", "params", "interrupted"]

    def __init__(self, path: Path):
        self.path = path
        with open(path, "w", newline="") as f:
            csv.writer(f, lineterminator="\n").writerow(self.HEADER)

    def write(self, event: Event):
        with open(self.path, "a", newline="") as f:
            csv.writer(f, lineterminator="\n").writerow([
                event.event_id, event.kind, event.target, utc_iso(event.start), utc_iso(event.end),
                json.dumps(event.params, sort_keys=True), str(event.interrupted).lower(),
            ])


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Traffic + labelled-anomaly generator for the SNMP testbed")
    p.add_argument("--hours", type=float, help="stop after this many hours (default: run until Ctrl+C)")
    p.add_argument("--day-minutes", type=float, default=1440,
                   help="real minutes per simulated 24 h load cycle (default 1440 = real time)")
    p.add_argument("--start-hour", type=float, help="simulated hour of day to start at (default: current local hour)")
    p.add_argument("--peak-mbps", type=float, default=8.0, help="UDP rate per link at load 1.0 (default 8)")
    p.add_argument("--cycle", type=int, default=10, help="seconds per traffic cycle (default 10)")
    p.add_argument("--anomaly-every", type=float, default=30.0,
                   help="mean minutes between anomalies (default 30; one at a time, never overlapping)")
    p.add_argument("--first-anomaly-after", type=float, default=10.0,
                   help="minutes of clean traffic before the first anomaly (default 10)")
    p.add_argument("--no-anomalies", action="store_true", help="generate normal traffic only")
    p.add_argument("--seed", type=int, help="random seed, for reproducible runs")
    p.add_argument("--output-dir", default=str(Path(__file__).resolve().parent / "runs"))
    return p.parse_args(argv)


def run(args):
    if not containers_running():
        sys.exit("Testbed containers are not running. Start them first:\n"
                 "  docker compose -f testbed/docker-compose.yml up -d --build")

    seed = args.seed if args.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    netem_ok = netem_supported()
    if not netem_ok and not args.no_anomalies:
        print("tc netem is not available in this kernel: packet-loss and latency anomalies are disabled.")

    run_dir = Path(args.output_dir) / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)
    truth = GroundTruth(run_dir / "ground_truth.csv")
    t0 = time.time()
    start_hour = args.start_hour if args.start_hour is not None else (
        datetime.now().hour + datetime.now().minute / 60)
    (run_dir / "meta.json").write_text(json.dumps({
        "started_utc": utc_iso(t0), "seed": seed, "netem_available": netem_ok,
        "args": {k: v for k, v in vars(args).items()}, "start_hour": start_hour,
    }, indent=2))
    print(f"Run directory: {run_dir}\nSeed: {seed}  (Ctrl+C to stop)")

    stop = {"flag": False}
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.update(flag=True))

    deadline = t0 + args.hours * 3600 if args.hours else None
    sim_speed = 1440.0 / args.day_minutes
    active = None
    next_id = 1
    next_event_at = t0 + args.first_anomaly_after * 60
    procs = []

    try:
        while not stop["flag"] and (deadline is None or time.time() < deadline):
            cycle_start = time.time()

            if active and cycle_start >= active.end:
                if not active.is_pair_event:
                    clear_netem(active.target)
                # Label the moment traffic really returned to normal (this
                # cycle boundary), not the planned end up to one cycle earlier.
                active.end = cycle_start
                truth.write(active)
                print(f"[{utc_iso(cycle_start)}] anomaly #{active.event_id} ended")
                next_event_at = cycle_start + rng.expovariate(1 / (args.anomaly_every * 60)) + 120
                active = None
            if not active and not args.no_anomalies and cycle_start >= next_event_at:
                active = plan_event(rng, next_id, cycle_start, netem_ok)
                next_id += 1
                if not active.is_pair_event:
                    apply_netem(active)
                print(f"[{utc_iso(cycle_start)}] anomaly #{active.event_id} {active.kind} on {active.target} "
                      f"for {(active.end - active.start) / 60:.1f} min")

            hour = start_hour + (cycle_start - t0) * sim_speed / 3600
            for client, server in RING:
                rate = (args.peak_mbps * load_at(hour) * max(0.05, rng.gauss(1.0, 0.15))
                        * pair_multiplier(active, client, server))
                if rate >= 0.05:
                    procs.append(subprocess.Popen(
                        [DOCKER, "exec", client, "iperf3", "-c", server, "-u", "-b", f"{rate:.2f}M",
                         "-t", str(max(1, args.cycle - 1))],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            procs = [p for p in procs if p.poll() is None]

            while not stop["flag"] and time.time() < cycle_start + args.cycle:
                time.sleep(0.25)
    finally:
        if active:
            active.end = time.time()
            active.interrupted = True
            if not active.is_pair_event:
                clear_netem(active.target)
            truth.write(active)
        for node in NODES:
            clear_netem(node)
        for p in procs:
            p.terminate()
        print(f"Stopped. Ground truth: {truth.path}")


if __name__ == "__main__":
    run(parse_args())
