from app import config
from app.models.device import Device
from app.segments import parse_segments, scannable_segments, segment_for_ip


def test_default_segments_label_both_subnets_and_testbed():
    assert segment_for_ip("192.168.1.24") == "wired"
    assert segment_for_ip("192.168.110.7") == "wireless"
    assert segment_for_ip("127.0.0.1") == "testbed"
    assert segment_for_ip("10.9.9.9") == "other"


def test_invalid_ip_is_other_not_an_error():
    assert segment_for_ip("not-an-ip") == "other"
    assert segment_for_ip("") == "other"


def test_malformed_entries_are_skipped():
    parsed = parse_segments("wired=192.168.1.0/24, broken, bad=999.1.1.1/8, wifi=10.0.0.0/8")
    assert [name for name, _ in parsed] == ["wired", "wifi"]


def test_segment_follows_config_changes(monkeypatch):
    monkeypatch.setattr(config, "NETWORK_SEGMENTS", "guest=10.20.0.0/16")
    assert segment_for_ip("10.20.3.4") == "guest"
    assert segment_for_ip("192.168.1.24") == "other"


def test_scan_presets_exclude_loopback_and_oversized_ranges(monkeypatch):
    monkeypatch.setattr(config, "NETWORK_SEGMENTS", "wired=192.168.1.0/24,big=10.0.0.0/8,testbed=127.0.0.0/8")
    assert scannable_segments() == [("wired", "192.168.1.0/24")]


def test_device_segment_property():
    assert Device(ip_address="192.168.110.20").segment == "wireless"
