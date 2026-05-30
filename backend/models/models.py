import uuid
import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, Numeric, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from .base import Base, TimestampMixin


class SeverityEnum(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IncidentStatusEnum(str, enum.Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"


class TransactionStatusEnum(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    HIGH_LATENCY = "HIGH_LATENCY"
    WEBHOOK_RETRY = "WEBHOOK_RETRY"
    PSP_TIMEOUT = "PSP_TIMEOUT"
    BANK_DOWN = "BANK_DOWN"


class Merchant(Base, TimestampMixin):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)

    transactions: Mapped[List["Transaction"]] = relationship(back_populates="merchant")


class PSP(Base):
    __tablename__ = "psps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    transactions: Mapped[List["Transaction"]] = relationship(back_populates="psp")
    incidents: Mapped[List["Incident"]] = relationship(back_populates="psp")


class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    transactions: Mapped[List["Transaction"]] = relationship(back_populates="bank")
    incidents: Mapped[List["Incident"]] = relationship(back_populates="bank")


class PaymentRail(Base):
    __tablename__ = "payment_rails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    transactions: Mapped[List["Transaction"]] = relationship(back_populates="rail")


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    psp_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("psps.id"), nullable=False)
    bank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=False)
    rail_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_rails.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True)

    merchant: Mapped["Merchant"] = relationship(back_populates="transactions")
    psp: Mapped["PSP"] = relationship(back_populates="transactions")
    bank: Mapped["Bank"] = relationship(back_populates="transactions")
    rail: Mapped["PaymentRail"] = relationship(back_populates="transactions")
    incident_links: Mapped[List["IncidentTransaction"]] = relationship(back_populates="transaction")

    __table_args__ = (
        Index("ix_transactions_psp_created", "psp_id", "created_at"),
        Index("ix_transactions_incident_status", "incident_id", "status"),
        Index("ix_transactions_merchant_created", "merchant_id", "created_at"),
    )


class Incident(Base, TimestampMixin):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    psp_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("psps.id"), nullable=True)
    bank_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    psp: Mapped[Optional["PSP"]] = relationship(back_populates="incidents")
    bank: Mapped[Optional["Bank"]] = relationship(back_populates="incidents")
    transaction_links: Mapped[List["IncidentTransaction"]] = relationship(back_populates="incident")
    chat_history: Mapped[List["IncidentChatHistory"]] = relationship(back_populates="incident")

    __table_args__ = (
        Index("ix_incidents_severity_status", "severity", "status"),
    )


class IncidentTransaction(Base):
    __tablename__ = "incident_transactions"

    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), primary_key=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id"), primary_key=True)

    incident: Mapped["Incident"] = relationship(back_populates="transaction_links")
    transaction: Mapped["Transaction"] = relationship(back_populates="incident_links")

    __table_args__ = (
        Index("ix_it_incident", "incident_id"),
        Index("ix_it_transaction", "transaction_id"),
    )


class IncidentChatHistory(Base, TimestampMixin):
    __tablename__ = "incident_chat_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # this was the bug — was pointing to wrong type before
    incident: Mapped["Incident"] = relationship(back_populates="chat_history")

    __table_args__ = (
        Index("ix_chat_incident_created", "incident_id", "created_at"),
    )