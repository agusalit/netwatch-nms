from sqlalchemy import Column, Integer, Boolean, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.models.database import Base


class StatusLog(Base):
    """
    One row per poll result (not just transitions) — kept small and pruned
    to STATUS_HISTORY_KEEP rows per device, enough for a response-time
    sparkline and a rolling uptime % without needing a time-series DB.
    """
    __tablename__ = "status_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    is_up = Column(Boolean, nullable=False)
    response_ms = Column(Float, nullable=True)
    checked_at = Column(DateTime, server_default=func.now(), nullable=False)

    device = relationship("Device", back_populates="status_logs")