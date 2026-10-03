"""
Exports NetWatch NMS data for offline analysis / ML work.

Writes devices, status_logs, and traffic_logs to CSV (default) or JSON,
with device metadata (name, ip, group) joined into each row so the
exported files are usable directly in pandas without needing to also
load the SQLite file separately.

Usage (run from the project root, with the venv active):
    python scripts/export_data.py
    python scripts/export_data.py --format json
    python scripts/export_data.py --device-id 1
    python scripts/export_data.py --since 2026-09-27
    python scripts/export_data.py --output-dir data/exports/run1
"""
import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.database import SessionLocal
from app.models.device import Device
from app.models.status_log import StatusLog
from app.models.traffic_log import TrafficLog


def _device_lookup(db, device_id=None):
    query = db.query(Device)
    if device_id:
        query = query.filter(Device.id == device_id)
    return {d.id: d for d in query.all()}


def _export_devices(devices, output_dir, fmt):
    rows = [{
        "id": d.id,
        "name": d.name,
        "ip_address": d.ip_address,
        "group": d.group.value,
        "monitor_type": d.monitor_type.value,
        "snmp_if_indexes": d.snmp_if_indexes,
    } for d in devices.values()]
    _write(rows, output_dir / f"devices.{fmt}", fmt)
    return len(rows)


def _export_status_logs(db, devices, output_dir, fmt, since):
    query = db.query(StatusLog).filter(StatusLog.device_id.in_(devices.keys()))
    if since:
        query = query.filter(StatusLog.checked_at >= since)
    logs = query.order_by(StatusLog.checked_at.asc()).all()

    rows = [{
        "id": s.id,
        "device_id": s.device_id,
        "device_name": devices[s.device_id].name,
        "device_ip": devices[s.device_id].ip_address,
        "device_group": devices[s.device_id].group.value,
        "checked_at_utc": s.checked_at.isoformat(),
        "is_up": s.is_up,
        "response_ms": s.response_ms,
    } for s in logs]
    _write(rows, output_dir / f"status_logs.{fmt}", fmt)
    return len(rows)


def _export_traffic_logs(db, devices, output_dir, fmt, since):
    query = db.query(TrafficLog).filter(TrafficLog.device_id.in_(devices.keys()))
    if since:
        query = query.filter(TrafficLog.recorded_at >= since)
    logs = query.order_by(TrafficLog.recorded_at.asc()).all()

    rows = [{
        "id": t.id,
        "device_id": t.device_id,
        "device_name": devices[t.device_id].name,
        "device_ip": devices[t.device_id].ip_address,
        "device_group": devices[t.device_id].group.value,
        "if_index": t.if_index,
        "recorded_at_utc": t.recorded_at.isoformat(),
        "in_octets": t.in_octets,
        "out_octets": t.out_octets,
        "in_errors": t.in_errors,
        "out_errors": t.out_errors,
        "in_discards": t.in_discards,
        "out_discards": t.out_discards,
    } for t in logs]
    _write(rows, output_dir / f"traffic_logs.{fmt}", fmt)
    return len(rows)


def _write(rows, path, fmt):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    if fmt == "json":
        with open(path, "w") as f:
            json.dump(rows, f, indent=2, default=str)
    else:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Export NetWatch NMS data for ML/analysis")
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument("--device-id", type=int, help="Only export one device")
    parser.add_argument("--since", type=str,
                         help="Only export rows at/after this UTC date/time "
                              "(e.g. 2026-09-27 or 2026-09-27T12:00:00)")
    parser.add_argument("--output-dir", type=str, default="data/exports")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since) if args.since else None
    output_dir = Path(args.output_dir)

    db = SessionLocal()
    try:
        devices = _device_lookup(db, args.device_id)
        if not devices:
            print("No matching devices found — nothing to export.")
            return

        n_devices = _export_devices(devices, output_dir, args.format)
        n_status = _export_status_logs(db, devices, output_dir, args.format, since)
        n_traffic = _export_traffic_logs(db, devices, output_dir, args.format, since)

        print(f"Exported to {output_dir}/ :")
        print(f"  devices.{args.format}       — {n_devices} rows")
        print(f"  status_logs.{args.format}   — {n_status} rows"
              + (" (StatusLog is pruned — only the current rolling window exists)" if n_status else ""))
        print(f"  traffic_logs.{args.format}  — {n_traffic} rows (full history, unpruned)")
    finally:
        db.close()


if __name__ == "__main__":
    main()