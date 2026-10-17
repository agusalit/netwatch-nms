"""
Bulk-adds monitoring targets from a CSV file, so a new network can be set up
in one step instead of one dialog per device.

CSV columns (header required; only name and ip_address are mandatory):
    name,ip_address,group,monitor_type,snmp_community,snmp_version,snmp_port,snmp_if_indexes
Lines starting with # and blank lines are ignored. See data/devices.example.csv.

Usage (run from the project root, with the venv active):
    python scripts/import_devices.py data/devices.csv --dry-run   # validate only
    python scripts/import_devices.py data/devices.csv
"""
import argparse
import csv
import ipaddress
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.database import SessionLocal, init_db
from app.models.device import Device, DeviceGroup, MonitorType
from app.segments import segment_for_ip


def _enum(enum_cls, raw, default, line_no, field):
    raw = (raw or "").strip()
    if not raw:
        return default
    for member in enum_cls:
        if raw.lower() in (member.value.lower(), member.name.lower()):
            return member
    allowed = ", ".join(m.value for m in enum_cls)
    raise ValueError(f"{field} '{raw}' is not one of: {allowed}")


def parse_row(row):
    name = (row.get("name") or "").strip()
    ip = (row.get("ip_address") or "").strip()
    if not name or not ip:
        raise ValueError("name and ip_address are required")
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"'{ip}' is not a valid IP address")
    port_raw = (row.get("snmp_port") or "").strip()
    try:
        port = int(port_raw) if port_raw else 161
    except ValueError:
        raise ValueError(f"snmp_port '{port_raw}' is not a number")
    version = (row.get("snmp_version") or "2c").strip() or "2c"
    if version not in ("1", "2c"):
        raise ValueError("snmp_version must be 1 or 2c")
    return dict(
        name=name,
        ip_address=ip,
        group=_enum(DeviceGroup, row.get("group"), DeviceGroup.OFFICE, 0, "group"),
        monitor_type=_enum(MonitorType, row.get("monitor_type"), MonitorType.ICMP, 0, "monitor_type"),
        snmp_community=(row.get("snmp_community") or "public").strip() or "public",
        snmp_version=version,
        snmp_port=port,
        snmp_if_indexes=(row.get("snmp_if_indexes") or "1").strip() or "1",
    )


def main():
    parser = argparse.ArgumentParser(description="Import monitoring targets from CSV")
    parser.add_argument("csv_file")
    parser.add_argument("--dry-run", action="store_true", help="validate and report, write nothing")
    args = parser.parse_args()

    path = Path(args.csv_file)
    if not path.exists():
        sys.exit(f"File not found: {path}")

    with open(path, newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)

    init_db()
    db = SessionLocal()
    added = skipped = errors = 0
    try:
        existing = {(d.ip_address, d.snmp_port) for d in db.query(Device).all()}
        for line_no, row in enumerate(reader, start=2):
            try:
                fields = parse_row(row)
            except ValueError as exc:
                errors += 1
                print(f"  line {line_no}: skipped - {exc}")
                continue
            key = (fields["ip_address"], fields["snmp_port"])
            if key in existing:
                skipped += 1
                print(f"  {fields['ip_address']}:{fields['snmp_port']} ({fields['name']}): already exists, skipped")
                continue
            existing.add(key)
            added += 1
            print(f"  + {fields['name']:<24} {fields['ip_address']:<16} {fields['group'].value:<7} "
                  f"{fields['monitor_type'].value:<9} [{segment_for_ip(fields['ip_address'])}]")
            if not args.dry_run:
                db.add(Device(**fields))
        if not args.dry_run:
            db.commit()
    finally:
        db.close()

    verb = "would add" if args.dry_run else "added"
    print(f"\n{verb} {added}, already present {skipped}, invalid {errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
