"""
db.py – SQLAlchemy SQLite ORM für Bambusleitung Speedtest-History
"""
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = os.environ.get("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "speedtest.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class SpeedTestResult(Base):
    __tablename__ = "speedtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    target_ip = Column(String(255), nullable=False)
    target_port = Column(Integer, nullable=False)
    run_type = Column(String(10), nullable=False)  # "manual" | "auto"
    download_mbps = Column(Float, nullable=True)
    upload_mbps = Column(Float, nullable=True)
    jitter_ms = Column(Float, nullable=True)
    packet_loss_pct = Column(Float, nullable=True)
    duration_s = Column(Float, nullable=True)
    retransmits = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="success")  # "success" | "error"
    error_msg = Column(Text, nullable=True)
    raw_json = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "target_ip": self.target_ip,
            "target_port": self.target_port,
            "run_type": self.run_type,
            "download_mbps": self.download_mbps,
            "upload_mbps": self.upload_mbps,
            "jitter_ms": self.jitter_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "duration_s": self.duration_s,
            "retransmits": self.retransmits,
            "status": self.status,
            "error_msg": self.error_msg,
        }


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
