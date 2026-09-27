from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
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
    snmp_if_index: int = Form(1),
):
    device = Device(
        name=name,
        ip_address=ip_address,
        group=group,
        monitor_type=monitor_type,
        snmp_community=snmp_community,
        snmp_version=snmp_version,
        snmp_port=snmp_port,
        snmp_if_index=snmp_if_index,
    )
    db.add(device)
    db.commit()
    # Return the refreshed grid so HTMX can swap it straight back in.
    return templates.TemplateResponse(
        request=request,
        name="partials/device_grid.html",
        context={"grouped_devices": _grouped_devices(db)},
    )


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