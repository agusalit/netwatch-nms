from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.device import Device, DeviceGroup, MonitorType
from app.templating import templates

router = APIRouter()


def _grouped_devices(db: Session):
    """Returns {group_label: [devices]} in a fixed, sensible display order."""
    devices = db.query(Device).order_by(Device.name).all()
    grouped = {g.value: [] for g in DeviceGroup}
    for d in devices:
        grouped[d.group.value].append(d)
    return grouped


def _grid_response(request: Request, db: Session, error: str = ""):
    """Renders the device grid as the main HTMX-swapped content, plus an
    out-of-band update to the modal's #form-error div. On success, error=""
    clears any previously shown message; on a caught conflict (e.g. duplicate
    IP), error carries the message and the JS in dashboard.html keeps the
    modal open instead of closing it."""
    grid_html = templates.env.get_template("partials/device_grid.html").render(
        request=request, grouped_devices=_grouped_devices(db)
    )
    oob_html = f'<div id="form-error" hx-swap-oob="true" class="form-error">{error}</div>'
    return HTMLResponse(grid_html + oob_html)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "grouped_devices": _grouped_devices(db),
            "groups": list(DeviceGroup),
            "monitor_types": list(MonitorType),
        },
    )


@router.get("/partials/device-grid", response_class=HTMLResponse)
def device_grid(request: Request, db: Session = Depends(get_db)):
    """Polled by HTMX every few seconds to refresh live status without a full page reload."""
    return templates.TemplateResponse(
        request=request,
        name="partials/device_grid.html",
        context={"grouped_devices": _grouped_devices(db)},
    )


@router.get("/devices/new", response_class=HTMLResponse)
def new_device_form(request: Request):
    """Blank create form, loaded into the modal's swappable container."""
    return templates.TemplateResponse(
        request=request,
        name="partials/device_form.html",
        context={
            "device": None,
            "groups": list(DeviceGroup),
            "monitor_types": list(MonitorType),
        },
    )


@router.get("/devices/{device_id}/edit", response_class=HTMLResponse)
def edit_device_form(device_id: int, request: Request, db: Session = Depends(get_db)):
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
        return _grid_response(request, db, error=f"A device with IP {ip_address} already exists.")
    return _grid_response(request, db)


@router.put("/devices/{device_id}", response_class=HTMLResponse)
def update_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
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
        return _grid_response(request, db, error=f"A device with IP {ip_address} already exists.")
    return _grid_response(request, db)


@router.delete("/devices/{device_id}", response_class=HTMLResponse)
def delete_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if device:
        db.delete(device)
        db.commit()
    return templates.TemplateResponse(
        request=request,
        name="partials/device_grid.html",
        context={"grouped_devices": _grouped_devices(db)},
    )