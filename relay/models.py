"""
models.py - Standalone database models for Antigravity Voice Assistant Cloud Relay.
"""
import os
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Index
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("RELAY_DATABASE_URL", "sqlite:///./relay.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

DEFAULT_TENANT_ID = os.environ.get("RELAY_DEFAULT_TENANT", "antigravity_default")


class AgentDispatch(Base):
    __tablename__ = "agent_dispatches"

    id = Column(String(64), primary_key=True, default=lambda: f"disp_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), nullable=False, default=DEFAULT_TENANT_ID)
    instruction = Column(Text, nullable=False)
    status = Column(String(32), default="PENDING")  # PENDING, DELIVERED, EXECUTED, EXPIRED, FAILED
    source = Column(String(64), default="android_companion")
    client_id = Column(String(64), nullable=True)
    execution_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
    ttl_seconds = Column(Integer, default=300)

    __table_args__ = (
        Index("idx_agent_dispatch_tenant_status", "tenant_id", "status"),
    )


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
