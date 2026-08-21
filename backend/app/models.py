"""SQLAlchemy ORM models for LifePilot.

Covers: Users/Profiles, Opportunities (matched results), Documents checklist,
Deadlines, Agent run logs, and Sessions/Runs.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Eligibility-relevant attributes
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)  # General/OBC/SC/ST/EWS
    education_level: Mapped[str | None] = mapped_column(String(60), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(120), nullable=True)
    annual_income: Mapped[int | None] = mapped_column(Integer, nullable=True)  # in INR
    disability: Mapped[bool] = mapped_column(Boolean, default=False)
    goals: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    runs: Mapped[list["AgentRun"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    profile: Mapped["Profile"] = relationship(back_populates="runs")
    logs: Mapped[list["AgentLog"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    matches: Mapped[list["MatchResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped["AgentRun"] = relationship(back_populates="logs")


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))

    opportunity_id: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(240))
    provider: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(120), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(40), nullable=True)

    eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    reasons: Mapped[list] = mapped_column(JSON, default=list)
    unmet: Mapped[list] = mapped_column(JSON, default=list)
    documents: Mapped[list] = mapped_column(JSON, default=list)
    roadmap: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped["AgentRun"] = relationship(back_populates="matches")
