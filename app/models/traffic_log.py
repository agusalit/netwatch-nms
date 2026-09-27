from sqlalchemy import Column, Integer, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from app.models.database import Base


class TrafficLog(Base):
    """
    Raw IF-MIB interface counters, one row per SNMP poll of an SNMP-enabled
    device. Deliberately NOT pruned like StatusLog — this is the dataset the
    later ML anomaly-detection work will train on, so it needs full history.

    Counters are stored raw (cumulative since interface last reset), not as
    rates — computing bytes/sec deltas is left to the analysis/ML pipeline,
    which may want to frame that differently (e.g. per-minute vs per-poll-
    interval rates). Keeping the raw values here keeps this table reusable.
    """
    __tablename__ = "traffic_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    recorded_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)

    if_index = Column(Integer, nullable=False, default=1)
    in_octets = Column(BigInteger, nullable=True)
    out_octets = Column(BigInteger, nullable=True)
    in_errors = Column(BigInteger, nullable=True)
    out_errors = Column(BigInteger, nullable=True)
    in_discards = Column(BigInteger, nullable=True)
    out_discards = Column(BigInteger, nullable=True)

    device = relationship("Device", back_populates="traffic_logs")