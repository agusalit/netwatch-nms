import asyncio
import logging
from datetime import datetime

import requests
from icmplib import ping as icmp_ping
from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd, SnmpEngine, CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity,
)
from sqlalchemy.orm import Session

from app.config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    PING_TIMEOUT_SECONDS, STATUS_HISTORY_KEEP,
)
from app.models.database import SessionLocal
from app.models.device import Device, MonitorType
from app.models.status_log import StatusLog
from app.models.traffic_log import TrafficLog

logger = logging.getLogger("nms.polling")

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"

# IF-MIB interface counters — {index} is filled in per-interface at poll time,
# since a device may have multiple interfaces tracked (device.if_index_list).
IF_IN_OCTETS_OID = "1.3.6.1.2.1.2.2.1.10.{index}"
IF_OUT_OCTETS_OID = "1.3.6.1.2.1.2.2.1.16.{index}"
IF_IN_ERRORS_OID = "1.3.6.1.2.1.2.2.1.14.{index}"
IF_OUT_ERRORS_OID = "1.3.6.1.2.1.2.2.1.20.{index}"
IF_IN_DISCARDS_OID = "1.3.6.1.2.1.2.2.1.13.{index}"
IF_OUT_DISCARDS_OID = "1.3.6.1.2.1.2.2.1.19.{index}"


def check_icmp(ip_address: str):
    """Returns (is_up, response_ms). Uses an unprivileged (datagram) ICMP socket,
    which works without root/setcap on Linux as long as net.ipv4.ping_group_range
    permits it (check with: cat /proc/sys/net/ipv4/ping_group_range)."""
    try:
        result = icmp_ping(ip_address, count=1, timeout=PING_TIMEOUT_SECONDS, privileged=False)
        return result.is_alive, (result.avg_rtt if result.is_alive else None)
    except Exception as exc:
        logger.warning(f"ICMP check failed for {ip_address}: {exc}")
        return False, None


def _safe_int(varbind_value):
    """SNMP GET can return non-numeric error types (e.g. noSuchObject) for an
    OID the device doesn't support — coerce those to None instead of raising."""
    try:
        return int(varbind_value)
    except (ValueError, TypeError):
        return None


def _snmp_community(device: Device):
    return CommunityData(device.snmp_community, mpModel=0 if device.snmp_version == "1" else 1)


async def _check_snmp_sysinfo_async(device: Device):
    """One-time-per-poll sys info fetch (sysName, sysUpTime) — not per-interface."""
    try:
        transport = await UdpTransportTarget.create(
            (device.ip_address, device.snmp_port),
            timeout=PING_TIMEOUT_SECONDS,
            retries=0,
        )
        error_indication, error_status, _, var_binds = await get_cmd(
            SnmpEngine(),
            _snmp_community(device),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(SYS_NAME_OID)),
            ObjectType(ObjectIdentity(SYS_UPTIME_OID)),
        )
        if error_indication or error_status:
            logger.warning(
                f"SNMP sysinfo GET failed for {device.ip_address}: "
                f"error_indication={error_indication}, error_status={error_status}"
            )
            return None
        return {"sys_name": str(var_binds[0][1]), "sys_uptime": str(var_binds[1][1])}
    except Exception as exc:
        logger.warning(f"SNMP sysinfo check failed for {device.ip_address}: {exc}")
        return None


async def _check_snmp_interface_async(device: Device, if_index: int):
    """Interface counters for one ifIndex. Called once per interface in
    device.if_index_list, so a multi-interface device gets multiple TrafficLog
    rows per poll — one per interface."""
    try:
        transport = await UdpTransportTarget.create(
            (device.ip_address, device.snmp_port),
            timeout=PING_TIMEOUT_SECONDS,
            retries=0,
        )
        error_indication, error_status, _, var_binds = await get_cmd(
            SnmpEngine(),
            _snmp_community(device),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(IF_IN_OCTETS_OID.format(index=if_index))),
            ObjectType(ObjectIdentity(IF_OUT_OCTETS_OID.format(index=if_index))),
            ObjectType(ObjectIdentity(IF_IN_ERRORS_OID.format(index=if_index))),
            ObjectType(ObjectIdentity(IF_OUT_ERRORS_OID.format(index=if_index))),
            ObjectType(ObjectIdentity(IF_IN_DISCARDS_OID.format(index=if_index))),
            ObjectType(ObjectIdentity(IF_OUT_DISCARDS_OID.format(index=if_index))),
        )
        if error_indication or error_status:
            logger.warning(
                f"SNMP interface counters GET failed for {device.ip_address} "
                f"ifIndex={if_index}: error_indication={error_indication}, error_status={error_status}"
            )
            return None
        return {
            "in_octets": _safe_int(var_binds[0][1]),
            "out_octets": _safe_int(var_binds[1][1]),
            "in_errors": _safe_int(var_binds[2][1]),
            "out_errors": _safe_int(var_binds[3][1]),
            "in_discards": _safe_int(var_binds[4][1]),
            "out_discards": _safe_int(var_binds[5][1]),
        }
    except Exception as exc:
        logger.warning(f"SNMP interface check failed for {device.ip_address} ifIndex={if_index}: {exc}")
        return None


async def _check_snmp_all_async(device: Device):
    sysinfo = await _check_snmp_sysinfo_async(device)
    interfaces = {}
    for idx in device.if_index_list:
        counters = await _check_snmp_interface_async(device, idx)
        if counters:
            interfaces[idx] = counters
    return {"sysinfo": sysinfo, "interfaces": interfaces}


def check_snmp(device: Device):
    """Sync wrapper around the async pysnmp 7.x calls. Safe to call with
    asyncio.run() here because APScheduler runs jobs in a worker thread,
    not on FastAPI's event loop, so there's no already-running-loop conflict.
    Returns {"sysinfo": {...} | None, "interfaces": {if_index: {...counters}}}."""
    return asyncio.run(_check_snmp_all_async(device))


def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception as exc:
        logger.warning(f"Telegram alert failed: {exc}")


def trim_history(db: Session, device_id: int):
    """Keep only the most recent STATUS_HISTORY_KEEP rows per device."""
    logs = (
        db.query(StatusLog)
        .filter(StatusLog.device_id == device_id)
        .order_by(StatusLog.checked_at.desc())
        .offset(STATUS_HISTORY_KEEP)
        .all()
    )
    for log in logs:
        db.delete(log)


def poll_all_devices():
    """The APScheduler job — one full sweep over every registered device."""
    db: Session = SessionLocal()
    try:
        devices = db.query(Device).all()
        for device in devices:
            was_up = device.is_up
            is_up, response_ms = check_icmp(device.ip_address)

            if is_up and device.monitor_type == MonitorType.ICMP_SNMP:
                snmp_result = check_snmp(device)
                if snmp_result["sysinfo"]:
                    device.snmp_sys_name = snmp_result["sysinfo"]["sys_name"]
                    device.snmp_uptime = snmp_result["sysinfo"]["sys_uptime"]
                for idx, counters in snmp_result["interfaces"].items():
                    db.add(TrafficLog(
                        device_id=device.id,
                        if_index=idx,
                        in_octets=counters["in_octets"],
                        out_octets=counters["out_octets"],
                        in_errors=counters["in_errors"],
                        out_errors=counters["out_errors"],
                        in_discards=counters["in_discards"],
                        out_discards=counters["out_discards"],
                    ))

            device.is_up = is_up
            device.last_response_ms = response_ms
            device.last_checked_at = datetime.utcnow()

            db.add(StatusLog(device_id=device.id, is_up=is_up, response_ms=response_ms))
            trim_history(db, device.id)

            # Alert only on a genuine transition, not on every poll,
            # and not on the very first check (was_up is None).
            if was_up is not None and was_up != is_up:
                state = "🟢 UP" if is_up else "🔴 DOWN"
                send_telegram_alert(f"{state}: {device.name} ({device.ip_address})")

        db.commit()
    except Exception as exc:
        logger.error(f"Polling sweep failed: {exc}")
        db.rollback()
    finally:
        db.close()