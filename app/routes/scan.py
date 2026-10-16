import ipaddress
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from icmplib import multiping
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import PING_TIMEOUT_SECONDS
from app.models.database import get_db
from app.models.device import Device
from app.segments import scannable_segments
from app.templating import templates

router = APIRouter()
logger = logging.getLogger("nms.scan")

MAX_SCAN_HOSTS = 256


def _render(request: Request, **context):
    context.setdefault("cidr", "")
    context.setdefault("error", None)
    context.setdefault("results", None)
    context["segments"] = scannable_segments()
    return templates.TemplateResponse(request=request, name="partials/scan_form.html", context=context)


@router.get("/scan/new", response_class=HTMLResponse)
def scan_form(request: Request, user: str = Depends(require_login)):
    return _render(request)


@router.post("/scan", response_class=HTMLResponse)
def run_scan(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(require_login),
    cidr: str = Form(...),
):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return _render(
            request,
            cidr=cidr,
            error=f"'{cidr}' is not a valid network range (e.g. 192.168.1.0/24).",
        )

    if network.num_addresses > MAX_SCAN_HOSTS:
        return _render(
            request,
            cidr=cidr,
            error=f"Range too large ({network.num_addresses} addresses) — "
                  f"max {MAX_SCAN_HOSTS} (a /24 or smaller).",
        )

    addresses = [str(ip) for ip in network.hosts()]
    existing_ips = {row[0] for row in db.query(Device.ip_address).all()}

    hosts = multiping(addresses, count=1, timeout=PING_TIMEOUT_SECONDS, privileged=False)

    discovered = [
        {"ip": h.address, "response_ms": round(h.avg_rtt, 1) if h.avg_rtt else None}
        for h in hosts
        if h.is_alive and h.address not in existing_ips
    ]
    discovered.sort(key=lambda d: tuple(int(p) for p in d["ip"].split(".")))

    return _render(
        request,
        cidr=cidr,
        results=discovered,
        scanned_count=len(addresses),
    )
