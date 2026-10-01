"""
Data completeness report for NetWatch NMS.

Analyzes StatusLog and TrafficLog history per device and reports how
reliable the collected data actually is — expected vs. actual reading
counts, gap detection, and uptime over the observed window. Intended as
supporting evidence for a thesis methodology section ("the data pipeline
is reliable enough to build on"), not as an app feature.

Usage (run from the project root, with the venv active):
    python scripts/data_quality_report.py
    python scripts/data_quality_report.py --device-id 1
    python scripts/data_quality_report.py --gap-threshold 3
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running this script directly (python scripts/data_quality_report.py)
# without needing the project installed as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import PING_INTERVAL_SECONDS
from app.models.database import SessionLocal
from app.models.device import Device
from app.models.status_log import StatusLog
from app.models.traffic_log import TrafficLog


def analyze_device(db, device: Device, gap_threshold_multiplier: float):
    status_logs = (
        db.query(StatusLog)
        .filter(StatusLog.device_id == device.id)
        .order_by(StatusLog.checked_at.asc())
        .all()
    )
    traffic_logs = (
        db.query(TrafficLog)
        .filter(TrafficLog.device_id == device.id)
        .order_by(TrafficLog.recorded_at.asc())
        .all()
    )

    print(f"\n=== Device: {device.name} ({device.ip_address}) [{device.group.value}] ===")

    if not status_logs:
        print("  No status history yet.")
        return

    first, last = status_logs[0].checked_at, status_logs[-1].checked_at
    span_seconds = (last - first).total_seconds()
    expected_readings = max(1, int(span_seconds / PING_INTERVAL_SECONDS) + 1)
    actual_readings = len(status_logs)
    completeness_pct = min(100.0, round((actual_readings / expected_readings) * 100, 1))

    up_count = sum(1 for s in status_logs if s.is_up)
    uptime_pct = round((up_count / actual_readings) * 100, 1)

    print(f"  StatusLog window (UTC): {first} -> {last}  ({span_seconds / 60:.1f} min)")
    print(f"  Readings: {actual_readings} actual / ~{expected_readings} expected "
          f"-> {completeness_pct}% completeness")
    print(f"  Uptime over window: {uptime_pct}%")

    # NOTE: StatusLog is pruned to STATUS_HISTORY_KEEP rows — this completeness
    # figure reflects only the current rolling window, not full project history.
    # TrafficLog is NOT pruned, so its count below reflects true total history.

    gaps = []
    threshold = PING_INTERVAL_SECONDS * gap_threshold_multiplier
    for prev, curr in zip(status_logs, status_logs[1:]):
        delta = (curr.checked_at - prev.checked_at).total_seconds()
        if delta > threshold:
            gaps.append((prev.checked_at, curr.checked_at, delta))

    if gaps:
        print(f"  Gaps (> {gap_threshold_multiplier}x poll interval, times in UTC): {len(gaps)}")
        for start, end, delta in gaps[:5]:
            print(f"    {start} -> {end}  ({delta:.0f}s, app likely down or restarted)")
        if len(gaps) > 5:
            print(f"    ... and {len(gaps) - 5} more")
    else:
        print("  No significant gaps detected.")

    if device.monitor_type.value == "icmp_snmp":
        if traffic_logs:
            t_first, t_last = traffic_logs[0].recorded_at, traffic_logs[-1].recorded_at
            print(f"  TrafficLog (UTC): {len(traffic_logs)} total rows, {t_first} -> {t_last}")
            missing_counters = sum(1 for t in traffic_logs if t.in_octets is None)
            if missing_counters:
                print(f"  WARNING: {missing_counters}/{len(traffic_logs)} rows have no "
                      f"in_octets — this device's SNMP agent may not expose IF-MIB counters.")
        else:
            print("  TrafficLog: no rows yet (SNMP never succeeded for this device).")


def main():
    parser = argparse.ArgumentParser(description="NetWatch NMS data completeness report")
    parser.add_argument("--device-id", type=int, help="Only report on one device")
    parser.add_argument("--gap-threshold", type=float, default=3.0,
                         help="Flag a gap when the time between readings exceeds this "
                              "multiple of PING_INTERVAL_SECONDS (default: 3)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Device)
        if args.device_id:
            query = query.filter(Device.id == args.device_id)
        devices = query.order_by(Device.name).all()

        if not devices:
            print("No devices found.")
            return

        print(f"NetWatch NMS — Data Completeness Report")
        print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
        print(f"Configured poll interval: {PING_INTERVAL_SECONDS}s")

        for device in devices:
            analyze_device(db, device, args.gap_threshold)
    finally:
        db.close()


if __name__ == "__main__":
    main()