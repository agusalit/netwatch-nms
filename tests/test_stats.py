from datetime import datetime, timedelta, timezone

from app.models.device import Device, DeviceGroup, MonitorType
from app.models.status_log import StatusLog
from app.routes.devices import _attach_stats


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_uptime_uses_24h_window_and_sparkline_uses_latest_readings(db_session):
    device = Device(name="StatsDev", ip_address="10.7.0.1", group=DeviceGroup.OFFICE, monitor_type=MonitorType.ICMP)
    db_session.add(device)
    db_session.commit()

    now = _now()
    # Older than 24 h: must not count towards uptime, but must still exist (nothing is pruned).
    for i in range(10):
        db_session.add(StatusLog(device_id=device.id, is_up=False, response_ms=None,
                                 checked_at=now - timedelta(hours=30, minutes=i)))
    # Inside the window: 3 up, 1 down -> 75 %
    for i, up in enumerate([True, True, True, False]):
        db_session.add(StatusLog(device_id=device.id, is_up=up, response_ms=5.0 + i if up else None,
                                 checked_at=now - timedelta(minutes=10 - i)))
    db_session.commit()

    _attach_stats(db_session, [device])
    assert device.uptime_pct == 75.0
    assert device.sparkline != ""
    assert db_session.query(StatusLog).filter(StatusLog.device_id == device.id).count() == 14


def test_no_recent_readings_gives_no_uptime(db_session):
    device = Device(name="QuietDev", ip_address="10.7.0.2", group=DeviceGroup.OFFICE, monitor_type=MonitorType.ICMP)
    db_session.add(device)
    db_session.commit()
    _attach_stats(db_session, [device])
    assert device.uptime_pct is None
    assert device.sparkline == ""
