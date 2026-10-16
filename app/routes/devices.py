from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import DISPLAY_TIMEZONE, STATUS_HISTORY_KEEP
from app.models.database import get_db
from app.models.device import Device, DeviceGroup, MonitorType
from app.models.status_log import StatusLog
from app.templating import templates

router = APIRouter()
_DISPLAY_TZ = ZoneInfo(DISPLAY_TIMEZONE)
UPTIME_WINDOW = timedelta(hours=24)


def _to_local(dt):
    """Converts a naive UTC datetime (as stored in the DB) to a tz-aware
    local datetime for display only. Storage stays UTC throughout — this
    is purely a presentation-layer conversion."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(_DISPLAY_TZ)


def _sparkline_points(values, width=60, height=20):
    """Turns a list of response-time floats into SVG polyline 'x,y ...' points,
    normalized to fit the given viewBox. Returns "" if there's not enough
    data to draw a meaningful line."""
    if not values or len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1
    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = (i / (n - 1)) * width
        y = height - ((v - lo) / rng) * height
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _attach_stats(db: Session, devices):
    """Attaches uptime_pct (last 24 h) and sparkline (latest STATUS_HISTORY_KEEP
    readings) to each device for the dashboard — computed, not persisted.

    StatusLog is never pruned, so nothing here may scan a device's whole
    history: uptime comes from one grouped query over a 24 h window, and the
    sparkline from one small LIMITed query per device. Both ride on the
    (device_id, checked_at) index."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - UPTIME_WINDOW
    rows = (
        db.query(
            StatusLog.device_id,
            func.count(StatusLog.id),
            func.sum(case((StatusLog.is_up.is_(True), 1), else_=0)),
        )
        .filter(StatusLog.checked_at >= since)
        .group_by(StatusLog.device_id)
        .all()
    )
    window = {device_id: (total, up or 0) for device_id, total, up in rows}

    for d in devices:
        total, up = window.get(d.id, (0, 0))
        d.uptime_pct = round(up / total * 100, 1) if total else None

        recent = (
            db.query(StatusLog.response_ms, StatusLog.is_up)
            .filter(StatusLog.device_id == d.id)
            .order_by(StatusLog.checked_at.desc())
            .limit(STATUS_HISTORY_KEEP)
            .all()
        )
        response_history = [r.response_ms for r in reversed(recent) if r.is_up and r.response_ms is not None]
        d.sparkline = _sparkline_points(response_history)
        d.last_checked_local = _to_local(d.last_checked_at)
    return devices


def _grouped_devices(db: Session):
    """Returns {group_label: [devices]} in a fixed, sensible display order."""
    devices = db.query(Device).order_by(Device.name).all()
    _attach_stats(db, devices)
    grouped = {g.value: [] for g in DeviceGroup}
    for d in devices:
        grouped[d.group.value].append(d)
    return grouped


def _summary_counts(grouped):
    """Up/down/unknown/total counts across every group, for the dashboard's
    summary bar. Recomputed on every grid render (every 5s poll) so it's
    always current, not cached."""
    all_devices = [d for devs in grouped.values() for d in devs]
    return {
        "up": sum(1 for d in all_devices if d.is_up is True),
        "down": sum(1 for d in all_devices if d.is_up is False),
        "unknown": sum(1 for d in all_devices if d.is_up is None),
        "total": len(all_devices),
    }


def _grid_response(request: Request, db: Session, error: str = ""):
    """Renders the device grid as the main HTMX-swapped content, plus an
    out-of-band update to the modal's #form-error div. On success, error=""
    clears any previously shown message; on a caught conflict (e.g. duplicate
    IP), error carries the message and the JS in dashboard.html keeps the
    modal open instead of closing it."""
    grouped = _grouped_devices(db)
    grid_html = templates.env.get_template("partials/device_grid.html").render(
        request=request, grouped_devices=grouped, summary=_summary_counts(grouped)
    )
    oob_html = f'<div id="form-error" hx-swap-oob="true" class="form-error">{error}</div>'
    return HTMLResponse(grid_html + oob_html)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: str = Depends(require_login)):
    grouped = _grouped_devices(db)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "grouped_devices": grouped,
            "summary": _summary_counts(grouped),
            "groups": list(DeviceGroup),
            "monitor_types": list(MonitorType),
        },
    )


@router.get("/partials/device-grid", response_class=HTMLResponse)
def device_grid(request: Request, db: Session = Depends(get_db), user: str = Depends(require_login)):
    """Polled by HTMX every few seconds to refresh live status without a full page reload."""
    grouped = _grouped_devices(db)
    return templates.TemplateResponse(
        request=request,
        name="partials/device_grid.html",
        context={"grouped_devices": grouped, "summary": _summary_counts(grouped)},
    )


@router.get("/devices/new", response_class=HTMLResponse)
def new_device_form(request: Request, ip: str = "", user: str = Depends(require_login)):
    """Blank create form, loaded into the modal's swappable container.
    Accepts an optional ?ip= to prefill — used by the scan results' '+ Add'
    buttons so the user doesn't have to retype a discovered IP."""
    return templates.TemplateResponse(
        request=request,
        name="partials/device_form.html",
        context={
            "device": None,
            "prefill_ip": ip,
            "groups": list(DeviceGroup),
            "monitor_types": list(MonitorType),
        },
    )


@router.get("/devices/{device_id}/edit", response_class=HTMLResponse)
def edit_device_form(device_id: int, request: Request, db: Session = Depends(get_db), user: str = Depends(require_login)):
    """Pre-filled edit form for an existing device, loaded into the same container."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return templates.TemplateResponse(
        request=request,
        name="partials/device_form.html",
        context={
            "device": device,
            "groups": list(DeviceGroup),
            "monitor_types": list(MonitorType),
        },
    )


@router.post("/devices", response_class=HTMLResponse)
def create_device(
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(require_login),
    name: str = Form(...),
    ip_address: str = Form(...),
    group: DeviceGroup = Form(...),
    monitor_type: MonitorType = Form(...),
    snmp_community: str = Form("public"),
    snmp_version: str = Form("2c"),
    snmp_port: int = Form(161),
    snmp_if_indexes: str = Form("1"),
):
    device = Device(
        name=name,
        ip_address=ip_address,
        group=group,
        monitor_type=monitor_type,
        snmp_community=snmp_community,
        snmp_version=snmp_version,
        snmp_port=snmp_port,
        snmp_if_indexes=snmp_if_indexes,
    )
    db.add(device)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _grid_response(request, db, error=f"A device with IP {ip_address} and SNMP port {snmp_port} already exists.")
    return _grid_response(request, db)


@router.put("/devices/{device_id}", response_class=HTMLResponse)
def update_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(require_login),
    name: str = Form(...),
    ip_address: str = Form(...),
    group: DeviceGroup = Form(...),
    monitor_type: MonitorType = Form(...),
    snmp_community: str = Form("public"),
    snmp_version: str = Form("2c"),
    snmp_port: int = Form(161),
    snmp_if_indexes: str = Form("1"),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    device.name = name
    device.ip_address = ip_address
    device.group = group
    device.monitor_type = monitor_type
    device.snmp_community = snmp_community
    device.snmp_version = snmp_version
    device.snmp_port = snmp_port
    device.snmp_if_indexes = snmp_if_indexes

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _grid_response(request, db, error=f"A device with IP {ip_address} and SNMP port {snmp_port} already exists.")
    return _grid_response(request, db)


@router.delete("/devices/{device_id}", response_class=HTMLResponse)
def delete_device(device_id: int, request: Request, db: Session = Depends(get_db), user: str = Depends(require_login)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device:
        db.delete(device)
        db.commit()
    grouped = _grouped_devices(db)
    return templates.TemplateResponse(
        request=request,
        name="partials/device_grid.html",
        context={"grouped_devices": grouped, "summary": _summary_counts(grouped)},
    )
