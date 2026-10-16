from sqlalchemy import Column, Integer, Boolean, Float, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import relationship

from app.models.database import Base


class StatusLog(Base):
    """
    One row per poll sweep per device, kept in full (never pruned): this is
    the real-network ICMP dataset. The dashboard only reads the latest
    STATUS_HISTORY_KEEP rows for the sparkline and a 24 h window for uptime %.

    response_ms is the average RTT of the sweep's PING_COUNT packets, jitter_ms
    the mean deviation between consecutive RTTs, packet_loss a 0..1 fraction.
    """
    __tablename__ = "status_logs"
    __table_args__ = (Index("ix_status_logs_device_checked", "device_id", "checked_at"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    is_up = Column(Boolean, nullable=False)
    response_ms = Column(Float, nullable=True)
    jitter_ms = Column(Float, nullable=True)
    packet_loss = Column(Float, nullable=True)
    checked_at = Column(DateTime, server_default=func.now(), nullable=False)

    device = relationship("Device", back_populates="status_logs")
