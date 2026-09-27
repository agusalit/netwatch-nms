import enum

from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Enum
from sqlalchemy.orm import relationship

from app.models.database import Base


class DeviceGroup(str, enum.Enum):
    ROOM = "Room"
    PUBLIC = "Public"
    OFFICE = "Office"


class MonitorType(str, enum.Enum):
    ICMP = "icmp"
    ICMP_SNMP = "icmp_snmp"


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    group = Column(Enum(DeviceGroup), default=DeviceGroup.ROOM, nullable=False)
    monitor_type = Column(Enum(MonitorType), default=MonitorType.ICMP, nullable=False)

    # SNMP config — only relevant when monitor_type == ICMP_SNMP
    snmp_community = Column(String, default="public")
    snmp_version = Column(String, default="2c")  # "1", "2c", or "3"
    snmp_port = Column(Integer, default=161)
    # Which network interface(s)' counters to poll on this device (IF-MIB
    # ifIndex values). Comma-separated so one device can have multiple
    # interfaces tracked (e.g. a managed switch) — each gets its own
    # TrafficLog row per poll. Defaults to "1", the common single-interface case.
    snmp_if_indexes = Column(String, default="1")

    # Live status, updated by the polling service
    is_up = Column(Boolean, default=None, nullable=True)  # None = not yet checked
    last_response_ms = Column(Float, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    snmp_sys_name = Column(String, nullable=True)
    snmp_uptime = Column(String, nullable=True)

    status_logs = relationship(
        "StatusLog", back_populates="device", cascade="all, delete-orphan"
    )
    traffic_logs = relationship(
        "TrafficLog", back_populates="device", cascade="all, delete-orphan"
    )

    @property
    def if_index_list(self):
        """Parses snmp_if_indexes ("1,2,4") into [1, 2, 4]. Falls back to
        [1] if the field is empty or contains no valid integers."""
        if not self.snmp_if_indexes:
            return [1]
        parsed = [
            int(part.strip()) for part in self.snmp_if_indexes.split(",")
            if part.strip().isdigit()
        ]
        return parsed or [1]