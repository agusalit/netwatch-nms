import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import import_devices  # noqa: E402
from app.models.device import DeviceGroup, MonitorType  # noqa: E402


def test_minimal_row_gets_defaults():
    fields = import_devices.parse_row({"name": "Switch", "ip_address": "192.168.1.2"})
    assert fields["group"] == DeviceGroup.OFFICE
    assert fields["monitor_type"] == MonitorType.ICMP
    assert (fields["snmp_community"], fields["snmp_version"], fields["snmp_port"]) == ("public", "2c", 161)


def test_full_row_and_case_insensitive_enums():
    fields = import_devices.parse_row({
        "name": "Core", "ip_address": "127.0.0.1", "group": "testbed", "monitor_type": "ICMP_SNMP",
        "snmp_community": "x", "snmp_version": "1", "snmp_port": "1161", "snmp_if_indexes": "2,4",
    })
    assert fields["group"] == DeviceGroup.TESTBED
    assert fields["monitor_type"] == MonitorType.ICMP_SNMP
    assert (fields["snmp_port"], fields["snmp_if_indexes"]) == (1161, "2,4")


@pytest.mark.parametrize("row, message", [
    ({"name": "", "ip_address": "1.1.1.1"}, "required"),
    ({"name": "A", "ip_address": "999.1.1.1"}, "valid IP"),
    ({"name": "A", "ip_address": "1.1.1.1", "group": "Lobby"}, "group"),
    ({"name": "A", "ip_address": "1.1.1.1", "snmp_port": "abc"}, "snmp_port"),
    ({"name": "A", "ip_address": "1.1.1.1", "snmp_version": "3"}, "snmp_version"),
])
def test_invalid_rows_are_rejected_with_a_reason(row, message):
    with pytest.raises(ValueError, match=message):
        import_devices.parse_row(row)
