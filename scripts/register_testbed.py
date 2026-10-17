"""
Registers the SNMP testbed nodes (testbed/docker-compose.yml) as monitoring
targets. It asks each node which ifIndex its eth0 has - that number differs
between Docker setups - so nothing needs to be looked up by hand.

Usage (run from the project root, with the venv active, testbed running):
    python scripts/register_testbed.py
    python scripts/register_testbed.py --nodes 3 --base-port 1161
"""
import argparse
import asyncio
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from discover_interfaces import discover  # noqa: E402
from app.models.database import SessionLocal, init_db  # noqa: E402
from app.models.device import Device, DeviceGroup, MonitorType  # noqa: E402


def pick_data_interface(descr, status, names):
    """eth0 if the node has one, else the first non-loopback interface that is up."""
    for index in sorted(descr):
        if (names.get(index) or descr[index]) == "eth0":
            return index
    for index in sorted(descr):
        if (names.get(index) or descr[index]) != "lo" and status.get(index) == "1":
            return index
    return None


def main():
    parser = argparse.ArgumentParser(description="Register the SNMP testbed nodes as devices")
    parser.add_argument("--nodes", type=int, default=3)
    parser.add_argument("--base-port", type=int, default=1161)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--community", default="public")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    failed = 0
    try:
        for i in range(args.nodes):
            port = args.base_port + i
            probe = Namespace(ip=args.host, port=port, community=args.community, version="2c")
            try:
                descr, status, names, _ = asyncio.run(discover(probe))
            except RuntimeError as exc:
                failed += 1
                print(f"  node {i + 1} ({args.host}:{port}): no SNMP answer ({exc}). Is the testbed running?")
                continue
            index = pick_data_interface(descr, status, names)
            if index is None:
                failed += 1
                print(f"  node {i + 1} ({args.host}:{port}): no usable interface found")
                continue

            device = db.query(Device).filter(Device.ip_address == args.host, Device.snmp_port == port).first()
            action = "updated"
            if device is None:
                device = Device(name=f"Testbed Node {i + 1}", ip_address=args.host, snmp_port=port)
                db.add(device)
                action = "added"
            device.group = DeviceGroup.TESTBED
            device.monitor_type = MonitorType.ICMP_SNMP
            device.snmp_community = args.community
            device.snmp_version = "2c"
            device.snmp_if_indexes = str(index)
            print(f"  {action} {device.name}: {args.host}:{port}, polling ifIndex {index} "
                  f"({names.get(index) or descr[index]})")
        db.commit()
    finally:
        db.close()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
