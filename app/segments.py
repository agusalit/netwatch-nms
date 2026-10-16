"""Network segment labelling (wired / wireless / testbed ...), derived from the
device IP and the NETWORK_SEGMENTS setting. Pure functions, no database."""
import ipaddress
from functools import lru_cache

from app import config


@lru_cache(maxsize=8)
def _parse_cached(spec: str):
    segments = []
    for part in spec.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        name, cidr = part.split("=", 1)
        try:
            network = ipaddress.ip_network(cidr.strip(), strict=False)
        except ValueError:
            continue
        segments.append((name.strip().lower(), network))
    return tuple(segments)


def parse_segments(spec: str):
    """'wired=192.168.1.0/24,wireless=192.168.110.0/24' -> [(name, ip_network), ...].
    Malformed entries are skipped instead of raising, so a typo in .env can't
    take the dashboard down."""
    return list(_parse_cached(spec))


def get_segments():
    return parse_segments(config.NETWORK_SEGMENTS)


def segment_for_ip(ip: str, segments=None) -> str:
    segments = get_segments() if segments is None else segments
    try:
        address = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return "other"
    for name, network in segments:
        if address.version == network.version and address in network:
            return name
    return "other"


def scannable_segments():
    """Segments worth offering as one-click scan presets: real networks of
    /24 or smaller (the scan cap), excluding loopback/testbed ranges."""
    return [
        (name, str(network))
        for name, network in get_segments()
        if network.version == 4 and network.num_addresses <= 256 and not network.is_loopback
    ]
