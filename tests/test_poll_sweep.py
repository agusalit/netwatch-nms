from app.models.device import Device, DeviceGroup, MonitorType
from app.models.status_log import StatusLog
from app.models.traffic_log import TrafficLog
from app.services import polling
from app.services.polling import IcmpResult


COUNTERS = {
    "in_octets": 1000, "out_octets": 2000, "in_errors": 0, "out_errors": 0,
    "in_discards": 0, "out_discards": 0, "counter_bits": 64,
}


def _make_device(session, name, ip, port=161, monitor=MonitorType.ICMP, indexes="1"):
    device = Device(name=name, ip_address=ip, snmp_port=port, group=DeviceGroup.TESTBED,
                    monitor_type=monitor, snmp_if_indexes=indexes)
    session.add(device)
    session.commit()
    return device.id


def _patch(monkeypatch, session_factory, icmp, snmp=None):
    monkeypatch.setattr(polling, "SessionLocal", session_factory)
    monkeypatch.setattr(polling, "ping_hosts", lambda addresses: {a: icmp(a) for a in addresses})
    monkeypatch.setattr(polling, "check_snmp_many", lambda devices: {d.id: snmp(d) for d in devices} if snmp else {})


def test_sweep_stores_latency_jitter_loss_and_traffic(monkeypatch, session_factory, db_session):
    device_id = _make_device(db_session, "SweepSnmp", "10.8.0.1", port=1161,
                             monitor=MonitorType.ICMP_SNMP, indexes="1,2")
    _patch(
        monkeypatch, session_factory,
        icmp=lambda a: IcmpResult(True, 4.2, 0.6, 0.25),
        snmp=lambda d: {"sysinfo": {"sys_name": "node", "sys_uptime": "123"},
                        "interfaces": {1: dict(COUNTERS), 2: dict(COUNTERS)}},
    )
    polling.poll_all_devices()
    db_session.expire_all()

    log = db_session.query(StatusLog).filter(StatusLog.device_id == device_id).one()
    assert (log.is_up, log.response_ms, log.jitter_ms, log.packet_loss) == (True, 4.2, 0.6, 0.25)
    traffic = db_session.query(TrafficLog).filter(TrafficLog.device_id == device_id).all()
    assert sorted(t.if_index for t in traffic) == [1, 2]
    assert all(t.counter_bits == 64 for t in traffic)
    assert db_session.get(Device, device_id).snmp_sys_name == "node"


def test_status_history_is_never_pruned(monkeypatch, session_factory, db_session):
    device_id = _make_device(db_session, "SweepKeep", "10.8.0.2")
    _patch(monkeypatch, session_factory, icmp=lambda a: IcmpResult(True, 1.0, 0.1, 0.0))
    for _ in range(45):  # well past the old 30-row pruning limit
        polling.poll_all_devices()
    assert db_session.query(StatusLog).filter(StatusLog.device_id == device_id).count() == 45


def test_down_device_is_logged_with_full_loss_and_no_snmp(monkeypatch, session_factory, db_session):
    device_id = _make_device(db_session, "SweepDown", "10.8.0.3", monitor=MonitorType.ICMP_SNMP)
    asked = []
    _patch(monkeypatch, session_factory,
           icmp=lambda a: IcmpResult(False, None, None, 1.0),
           snmp=lambda d: asked.append(d.id) or {"sysinfo": None, "interfaces": {}})
    polling.poll_all_devices()
    log = db_session.query(StatusLog).filter(StatusLog.device_id == device_id).one()
    assert (log.is_up, log.packet_loss) == (False, 1.0)
    assert device_id not in asked  # SNMP is only attempted for devices that answered ping


def test_alert_fires_on_transition_but_not_on_first_check(monkeypatch, session_factory, db_session):
    _make_device(db_session, "SweepAlert", "10.8.0.4")
    alerts = []
    monkeypatch.setattr(polling, "send_telegram_alert", alerts.append)
    state = {"up": True}
    _patch(monkeypatch, session_factory,
           icmp=lambda a: IcmpResult(state["up"], 1.0 if state["up"] else None, 0.0, 0.0 if state["up"] else 1.0))

    polling.poll_all_devices()                  # first check: no alert
    assert not [a for a in alerts if "SweepAlert" in a]
    state["up"] = False
    polling.poll_all_devices()                  # up -> down: alert
    assert [a for a in alerts if "SweepAlert" in a and "DOWN" in a]


def test_two_snmp_agents_behind_one_ip_are_distinct_devices(db_session):
    first = _make_device(db_session, "PortA", "10.8.0.5", port=2001, monitor=MonitorType.ICMP_SNMP)
    second = _make_device(db_session, "PortB", "10.8.0.5", port=2002, monitor=MonitorType.ICMP_SNMP)
    assert first != second
