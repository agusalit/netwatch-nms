from typing import Optional

from pydantic import BaseModel, Field

from app.models.device import DeviceGroup, MonitorType


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    ip_address: str = Field(min_length=1, max_length=45)
    group: DeviceGroup = DeviceGroup.ROOM
    monitor_type: MonitorType = MonitorType.ICMP
    snmp_community: Optional[str] = "public"
    snmp_version: Optional[str] = "2c"
    snmp_port: Optional[int] = 161


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    group: Optional[DeviceGroup] = None
    monitor_type: Optional[MonitorType] = None
    snmp_community: Optional[str] = None
    snmp_version: Optional[str] = None
    snmp_port: Optional[int] = None