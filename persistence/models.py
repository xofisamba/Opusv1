"""Persistence layer — SQLAlchemy ORM models for OpusCore v2.

Schema version 1: Projects, Scenarios, InputSnapshots, ResultSnapshots, ScenarioChangeLog.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import relationship, declarative_base, Mapped, mapped_column

Base = declarative_base()


class Project(Base):
    """A financial model project (Solar, Wind, BESS, Hybrid, etc.)."""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    technology_type: Mapped[str] = mapped_column(String, nullable=False)  # "solar"|"wind"|"bess"|"hybrid"|"agri"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # NULL until Phase 3 auth

    scenarios: Mapped[List["Scenario"]] = relationship(
        "Scenario",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Scenario.created_at",
    )


class Scenario(Base):
    """A scenario within a project — holds inputs snapshot + optional results."""
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    parent_scenario_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("scenarios.id"), nullable=True)
    is_base_case: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    description: Mapped[str] = mapped_column(String, default="")

    project: Mapped["Project"] = relationship("Project", back_populates="scenarios")
    parent: Mapped[Optional["Scenario"]] = relationship("Scenario", remote_side=[id], backref="children")

    input_snapshot: Mapped[Optional["InputSnapshot"]] = relationship(
        "InputSnapshot",
        back_populates="scenario",
        uselist=False,
        cascade="all, delete-orphan",
    )
    result_snapshot: Mapped[Optional["ResultSnapshot"]] = relationship(
        "ResultSnapshot",
        back_populates="scenario",
        uselist=False,
        cascade="all, delete-orphan",
    )


class InputSnapshot(Base):
    """Frozen inputs for a scenario (hash-keyed for cache invalidation)."""
    __tablename__ = "input_snapshots"

    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("scenarios.id"), primary_key=True)
    inputs_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    inputs_hash: Mapped[str] = mapped_column(String, nullable=False)  # SHA256 hex of inputs_json

    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="input_snapshot")


class ResultSnapshot(Base):
    """Cached waterfall result for a scenario."""
    __tablename__ = "result_snapshots"

    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("scenarios.id"), primary_key=True)
    results_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    inputs_hash: Mapped[str] = mapped_column(String, nullable=False)  # Must match InputSnapshot.inputs_hash

    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="result_snapshot")


class ScenarioChangeLog(Base):
    """Audit log for scenario input changes."""
    __tablename__ = "scenario_change_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(String, ForeignKey("scenarios.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    changed_by: Mapped[str] = mapped_column(String, default="user")
    diff_json: Mapped[Optional[dict]] = mapped_column(JSON)
    previous_inputs_hash: Mapped[Optional[str]] = mapped_column(String)
    new_inputs_hash: Mapped[Optional[str]] = mapped_column(String)