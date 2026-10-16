import enum

from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Enum, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base
from app.segments import segment_for_ip


class DeviceGroup(str, enum.Enum):
    ROOM = "Room"
    PUBLIC = "Public"
    OFFICE = "Office"
    TESTBED = "Testbed"


class MonitorType(str, enum.Enum):
    ICMP = "icmp"
    ICMP_SNMP = "icmp_snmp"


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("ip_address", "snmp_port", name="uq_device_ip_port"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False, index=True)
    group = Column(Enum(DeviceGroup), default=DeviceGroup.ROOM, nullable=False)
    monitor_type = Column(Enum(MonitorType), default=MonitorType.ICMP, nullable=False)
    snmp_community = Column(String, default="public")
    snmp_version = Column(String, default="2c")
    snmp_port = Column(Integer, default=161, nullable=False)
    snmp_if_indexes = Column(String, default="1")

    is_up = Column(Boolean, default=None, nullable=True)
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
    def segment(self):
        """wired / wireless / testbed / other — derived from the IP, never stored."""
        return segment_for_ip(self.ip_address)

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
