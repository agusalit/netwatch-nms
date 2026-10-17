"""
Lists the network interfaces an SNMP device exposes (ifIndex, name, status),
so you know which ifIndex values to enter in a device's "Interface Index(es)"
field — e.g. the gateway's wired and wireless interfaces.

Usage (run from the project root, with the venv active):
    python scripts/discover_interfaces.py 192.168.1.1 --community <read-community>
    python scripts/discover_interfaces.py 127.0.0.1 --port 1161          # a testbed node
    python scripts/discover_interfaces.py 192.168.1.1 --community x --version 1
"""
import argparse
import asyncio
import sys

from pysnmp.hlapi.v3arch.asyncio import (
    CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine,
    UdpTransportTarget, walk_cmd,
)

IF_DESCR_OID = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS_OID = "1.3.6.1.2.1.2.2.1.8"
IF_NAME_OID = "1.3.6.1.2.1.31.1.1.1.1"       # ifXTable, often a cleaner name than ifDescr
IF_HC_IN_OCTETS_OID = "1.3.6.1.2.1.31.1.1.1.6"

OPER_STATUS = {"1": "up", "2": "down", "3": "testing", "4": "unknown", "5": "dormant",
               "6": "notPresent", "7": "lowerLayerDown"}


async def _walk(engine, args, oid):
    transport = await UdpTransportTarget.create((args.ip, args.port), timeout=2, retries=1)
    rows = {}
    async for error_indication, error_status, _, var_binds in walk_cmd(
        engine,
        CommunityData(args.community, mpModel=0 if args.version == "1" else 1),
        transport,
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    ):
        if error_indication or error_status:
            raise RuntimeError(str(error_indication or error_status))
        for name, value in var_binds:
            index = int(str(name).rsplit(".", 1)[1])
            rows[index] = value.prettyPrint()
    return rows


async def discover(args):
    engine = SnmpEngine()
    try:
        descr = await _walk(engine, args, IF_DESCR_OID)
        status = await _walk(engine, args, IF_OPER_STATUS_OID)
        names, hc = {}, {}
        if args.version != "1":
            try:
                names = await _walk(engine, args, IF_NAME_OID)
                hc = await _walk(engine, args, IF_HC_IN_OCTETS_OID)
            except RuntimeError:
                pass  # agent has no ifXTable — the basic columns are enough
    finally:
        engine.close_dispatcher()
    return descr, status, names, hc


def main():
    parser = argparse.ArgumentParser(description="List SNMP interfaces (ifIndex) of a device")
    parser.add_argument("ip")
    parser.add_argument("--community", default="public")
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--version", choices=["1", "2c"], default="2c")
    args = parser.parse_args()

    try:
        descr, status, names, hc = asyncio.run(discover(args))
    except RuntimeError as exc:
        sys.exit(f"SNMP request to {args.ip}:{args.port} failed: {exc}\n"
                 "Check that SNMP is enabled, the community string, and that UDP port is reachable.")
    if not descr:
        sys.exit("The device answered but listed no interfaces.")

    print(f"Interfaces on {args.ip}:{args.port}")
    print(f"{'ifIndex':>8}  {'name':<24} {'status':<8} 64-bit counters")
    for index in sorted(descr):
        name = names.get(index) or descr[index]
        print(f"{index:>8}  {name:<24} {OPER_STATUS.get(status.get(index, ''), '?'):<8} "
              f"{'yes' if index in hc else 'no'}")
    print("\nEnter the ifIndex values you want as a comma-separated list, e.g. 1,5")


if __name__ == "__main__":
    main()
