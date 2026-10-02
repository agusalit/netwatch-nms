from app.services.polling import check_icmp, _safe_int


def test_safe_int_parses_valid_values():
    assert _safe_int("42") == 42
    assert _safe_int(42) == 42


def test_safe_int_returns_none_for_snmp_error_types():

    assert _safe_int("noSuchObject") is None
    assert _safe_int(None) is None


def test_check_icmp_localhost_is_reachable():
    is_up, response_ms = check_icmp("127.0.0.1")
    assert is_up is True
    assert response_ms is not None


def test_check_icmp_unreachable_address():

    is_up, response_ms = check_icmp("192.0.2.1")
    assert is_up is False
    assert response_ms is None