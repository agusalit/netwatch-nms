import asyncio
import ipaddress
import logging
from collections import namedtuple
from datetime import datetime, timezone

import requests
from icmplib import multiping
from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity,
)
from sqlalchemy.orm import Session

from app.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    PING_COUNT, PING_PACKET_INTERVAL_SECONDS, PING_TIMEOUT_SECONDS,
)
from app.models.database import SessionLocal
from app.models.device import Device, MonitorType
from app.models.status_log import StatusLog
from app.models.traffic_log import TrafficLog

logger = logging.getLogger("nms.polling")

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"
IF_IN_OCTETS_OID = "1.3.6.1.2.1.2.2.1.10.{index}"        # 
IF_OUT_OCTETS_OID = "1.3.6.1.2.1.2.2.1.16.{index}"
IF_IN_ERRORS_OID = "1.3.6.1.2.1.2.2.1.14.{index}"
IF_OUT_ERRORS_OID = "1.3.6.1.2.1.2.2.1.20.{index}"
IF_IN_DISCARDS_OID = "1.3.6.1.2.1.2.2.1.13.{index}"
IF_OUT_DISCARDS_OID = "1.3.6.1.2.1.2.2.1.19.{index}"
IF_HC_IN_OCTETS_OID = "1.3.6.1.2.1.31.1.1.1.6.{index}"
IF_HC_OUT_OCTETS_OID = "1.3.6.1.2.1.31.1.1.1.10.{index}"

IcmpResult = namedtuple("IcmpResult", "is_up response_ms jitter_ms packet_loss")
_DOWN = IcmpResult(False, None, None, 1.0)


def _utc_now():
    """Naive UTC datetime — the storage convention for every timestamp."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def ping_hosts(addresses):
    """Pings every unique address concurrently and returns {address: IcmpResult}.

    Each address gets PING_COUNT packets, so a result carries average latency,
    jitter and packet loss instead of one up/down sample. Uses unprivileged
    (datagram) ICMP sockets, which work without root/setcap on Linux as long as
    net.ipv4.ping_group_range permits it (check: cat /proc/sys/net/ipv4/ping_group_range).
    Every requested address always gets an entry; failures count as down.
    """
    unique = list(dict.fromkeys(addresses))
    results = {address: _DOWN for address in unique}
    valid = [a for a in unique if _is_ip(a)]
    for address in unique:
        if address not in valid:
            logger.warning(f"Skipping ICMP check: '{address}' is not a valid IP address")
    if not valid:
        return results
    try:
        hosts = multiping(
            valid,
            count=PING_COUNT,
            interval=PING_PACKET_INTERVAL_SECONDS,
            timeout=PING_TIMEOUT_SECONDS,
            privileged=False,
        )
    except Exception as exc:
        logger.warning(f"ICMP sweep failed: {exc}")
        return results
    for host in hosts:
        if host.is_alive:
            results[host.address] = IcmpResult(True, host.avg_rtt, host.jitter, host.packet_loss)
        else:
            results[host.address] = IcmpResult(False, None, None, host.packet_loss)
    return results


def check_icmp(ip_address: str):
    """Single-device convenience wrapper. Returns (is_up, response_ms)."""
    result = ping_hosts([ip_address])[ip_address]
    return result.is_up, result.response_ms


def _safe_int(varbind_value):
    """SNMP GET can return non-numeric error types (e.g. noSuchObject) for an
    OID the device doesn't support — coerce those to None instead of raising."""
    try:
        return int(varbind_value)
    except (ValueError, TypeError):
        return None


def _snmp_community(device: Device):
    return CommunityData(device.snmp_community, mpModel=0 if device.snmp_version == "1" else 1)


async def _snmp_get(engine, device: Device, oids, what: str):
    """One SNMP GET for several OIDs. Returns the varbinds, or None (and logs why)."""
    try:
        transport = await UdpTransportTarget.create(
            (device.ip_address, device.snmp_port),
            timeout=PING_TIMEOUT_SECONDS,
            retries=0,
        )
        error_indication, error_status, _, var_binds = await get_cmd(
            engine,
            _snmp_community(device),
            transport,
            ContextData(),
            *[ObjectType(ObjectIdentity(oid)) for oid in oids],
        )
        if error_indication or error_status:
            logger.warning(
                f"SNMP {what} GET failed for {device.ip_address}:{device.snmp_port}: "
                f"error_indication={error_indication}, error_status={error_status}"
            )
            return None
        return var_binds
    except Exception as exc:
        logger.warning(f"SNMP {what} check failed for {device.ip_address}:{device.snmp_port}: {exc}")
        return None


async def _check_snmp_sysinfo_async(engine, device: Device):
    """One-time-per-poll sys info fetch (sysName, sysUpTime) — not per-interface."""
    var_binds = await _snmp_get(engine, device, [SYS_NAME_OID, SYS_UPTIME_OID], "sysinfo")
    if var_binds is None:
        return None
    return {"sys_name": str(var_binds[0][1]), "sys_uptime": str(var_binds[1][1])}


async def _check_snmp_interface_async(engine, device: Device, if_index: int):
    """Interface counters for one ifIndex. Called once per interface in
    device.if_index_list, so a multi-interface device gets multiple TrafficLog
    rows per poll — one per interface.

    Octet counters prefer the 64-bit ifHC* values and fall back to the 32-bit
    ones; counter_bits records which one the row holds."""
    use_hc = device.snmp_version != "1"
    oids = [
        IF_IN_OCTETS_OID, IF_OUT_OCTETS_OID,
        IF_IN_ERRORS_OID, IF_OUT_ERRORS_OID,
        IF_IN_DISCARDS_OID, IF_OUT_DISCARDS_OID,
    ]
    if use_hc:
        oids += [IF_HC_IN_OCTETS_OID, IF_HC_OUT_OCTETS_OID]
    var_binds = await _snmp_get(
        engine, device, [oid.format(index=if_index) for oid in oids], f"ifIndex={if_index} counters"
    )
    if var_binds is None:
        return None
    values = [_safe_int(vb[1]) for vb in var_binds]
    in32, out32, in_err, out_err, in_disc, out_disc = values[:6]
    hc_in, hc_out = (values[6], values[7]) if use_hc else (None, None)
    if hc_in is not None and hc_out is not None:
        in_octets, out_octets, bits = hc_in, hc_out, 64
    else:
        in_octets, out_octets, bits = in32, out32, 32
    return {
        "in_octets": in_octets,
        "out_octets": out_octets,
        "in_errors": in_err,
        "out_errors": out_err,
        "in_discards": in_disc,
        "out_discards": out_disc,
        "counter_bits": bits,
    }


async def _check_snmp_device_async(engine, device: Device):
    sysinfo = await _check_snmp_sysinfo_async(engine, device)
    if sysinfo is None:
        return {"sysinfo": None, "interfaces": {}}
    indexes = device.if_index_list
    counters = await asyncio.gather(
        *[_check_snmp_interface_async(engine, device, idx) for idx in indexes]
    )
    return {
        "sysinfo": sysinfo,
        "interfaces": {idx: c for idx, c in zip(indexes, counters) if c},
    }


async def _check_snmp_many_async(devices):
    engine = SnmpEngine()
    try:
        results = await asyncio.gather(
            *[_check_snmp_device_async(engine, d) for d in devices], return_exceptions=True
        )
    finally:
        engine.close_dispatcher()
    out = {}
    for device, result in zip(devices, results):
        if isinstance(result, Exception):
            logger.warning(f"SNMP poll crashed for {device.ip_address}:{device.snmp_port}: {result}")
            result = {"sysinfo": None, "interfaces": {}}
        out[device.id] = result
    return out


def check_snmp_many(devices):
    """Polls every given device concurrently. Safe to call with asyncio.run()
    because APScheduler runs jobs in a worker thread, not on FastAPI's event
    loop. Returns {device.id: {"sysinfo": {...} | None, "interfaces": {if_index: {...}}}}."""
    if not devices:
        return {}
    return asyncio.run(_check_snmp_many_async(devices))


def check_snmp(device: Device):
    """Single-device convenience wrapper around check_snmp_many."""
    return check_snmp_many([device])[device.id]


def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception as exc:
        logger.warning(f"Telegram alert failed: {exc}")


def poll_all_devices():
    """The APScheduler job — one full sweep over every registered device.

    ICMP for all devices runs concurrently, then SNMP for every SNMP device
    that answered ping, also concurrently — so sweep time stays roughly
    constant as devices are added instead of growing linearly."""
    db: Session = SessionLocal()
    try:
        devices = db.query(Device).all()
        if not devices:
            return

        sweep_time = _utc_now()
        icmp = ping_hosts([d.ip_address for d in devices])
        snmp_targets = [
            d for d in devices
            if d.monitor_type == MonitorType.ICMP_SNMP and icmp.get(d.ip_address, _DOWN).is_up
        ]
        snmp = check_snmp_many(snmp_targets)
        snmp_time = _utc_now()

        for device in devices:
            was_up = device.is_up
            result = icmp.get(device.ip_address, _DOWN)

            snmp_result = snmp.get(device.id)
            if snmp_result:
                if snmp_result["sysinfo"]:
                    device.snmp_sys_name = snmp_result["sysinfo"]["sys_name"]
                    device.snmp_uptime = snmp_result["sysinfo"]["sys_uptime"]
                for idx, counters in snmp_result["interfaces"].items():
                    db.add(TrafficLog(device_id=device.id, if_index=idx, recorded_at=snmp_time, **counters))

            device.is_up = result.is_up
            device.last_response_ms = result.response_ms
            device.last_checked_at = sweep_time

            db.add(StatusLog(
                device_id=device.id,
                is_up=result.is_up,
                response_ms=result.response_ms,
                jitter_ms=result.jitter_ms,
                packet_loss=result.packet_loss,
                checked_at=sweep_time,
            ))

            if was_up is not None and was_up != result.is_up:
                state = "🟢 UP" if result.is_up else "🔴 DOWN"
                send_telegram_alert(f"{state}: {device.name} ({device.ip_address})")

        db.commit()
    except Exception as exc:
        logger.error(f"Polling sweep failed: {exc}")
        db.rollback()
    finally:
        db.close()
