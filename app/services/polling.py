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

logger = logging.getLogger("nms.polling")

SYS_NAME_OID = "1.3.6.1.2.1.1.5.0"
SYS_UPTIME_OID = "1.3.6.1.2.1.1.3.0"


def check_icmp(ip_address: str):
    """Returns (is_up, response_ms). privileged=False works without root/setcap
    on some systems but is slower; prefer setcap on the venv's python binary."""
    try:
        result = icmp_ping(ip_address, count=1, timeout=PING_TIMEOUT_SECONDS, privileged=True)
        return result.is_alive, (result.avg_rtt if result.is_alive else None)
    except Exception as exc:
        logger.warning(f"ICMP check failed for {ip_address}: {exc}")
        return False, None


async def _check_snmp_async(device: Device):
    try:
        transport = await UdpTransportTarget.create(
            (device.ip_address, device.snmp_port),
            timeout=PING_TIMEOUT_SECONDS,
            retries=0,
        )
        error_indication, error_status, _, var_binds = await get_cmd(
            SnmpEngine(),
            CommunityData(device.snmp_community, mpModel=0 if device.snmp_version == "1" else 1),
            transport,
            ContextData(),
            ObjectType(ObjectIdentity(SYS_NAME_OID)),
            ObjectType(ObjectIdentity(SYS_UPTIME_OID)),
        )
        if error_indication or error_status:
            return None, None
        sys_name = str(var_binds[0][1])
        sys_uptime = str(var_binds[1][1])
        return sys_name, sys_uptime
    except Exception as exc:
        logger.warning(f"SNMP check failed for {device.ip_address}: {exc}")
        return None, None


def check_snmp(device: Device):
    """Sync wrapper around the async pysnmp 7.x call. Safe to call with
    asyncio.run() here because APScheduler runs jobs in a worker thread,
    not on FastAPI's event loop, so there's no already-running-loop conflict."""
    return asyncio.run(_check_snmp_async(device))


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
                sys_name, sys_uptime = check_snmp(device)
                device.snmp_sys_name = sys_name
                device.snmp_uptime = sys_uptime

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