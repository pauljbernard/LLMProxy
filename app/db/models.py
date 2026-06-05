"""Canonical first-pass database models."""

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RequestLog(Base):
    __tablename__ = "request_log"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    requested_model: Mapped[str] = mapped_column(String)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
    task_type: Mapped[str | None] = mapped_column(String, nullable=True)
    request_json: Mapped[str] = mapped_column(Text)


class RoutingDecisionRecord(Base):
    __tablename__ = "routing_decision"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"))
    session_id: Mapped[str] = mapped_column(String)
    policy_version: Mapped[str] = mapped_column(String)
    selected_provider: Mapped[str] = mapped_column(String)
    selected_provider_family: Mapped[str] = mapped_column(String)
    selected_model: Mapped[str] = mapped_column(String)
    selected_mode: Mapped[str] = mapped_column(String)
    decision_rationale: Mapped[str] = mapped_column(Text)


class TrainingCandidate(Base):
    __tablename__ = "training_candidate"
    __table_args__ = {"schema": "proxy"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    request_log_id: Mapped[str] = mapped_column(ForeignKey("proxy.request_log.id"))
    routing_decision_id: Mapped[str] = mapped_column(ForeignKey("proxy.routing_decision.id"))
    session_id: Mapped[str] = mapped_column(String)
    domain: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    quality_score: Mapped[float] = mapped_column(Float)
    approval_status: Mapped[str] = mapped_column(String)
    export_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_response: Mapped[str] = mapped_column(Text)


class DatasetImport(Base):
    __tablename__ = "dataset_import"
    __table_args__ = {"schema": "learner"}

    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_export_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
