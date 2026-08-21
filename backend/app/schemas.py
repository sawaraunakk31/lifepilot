"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- Profile ----------
class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    age: int | None = Field(default=None, ge=5, le=120)
    gender: str | None = None
    state: str | None = None
    category: str | None = None  # General/OBC/SC/ST/EWS
    education_level: str | None = None
    field_of_study: str | None = None
    annual_income: int | None = Field(default=None, ge=0, le=100_000_000)
    disability: bool = False
    goals: str | None = None


class ProfileCreate(ProfileBase):
    pass


class ProfileOut(ProfileBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------- Agent run ----------
class AgentLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    agent: str
    message: str
    confidence: float | None = None
    created_at: datetime | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    opportunity_id: str
    title: str
    provider: str | None = None
    url: str | None = None
    amount: str | None = None
    deadline: str | None = None
    eligible: bool
    score: float
    confidence: float
    reasons: list[str] = []
    unmet: list[str] = []
    documents: list[str] = []
    roadmap: list[str] = []


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    profile_id: int
    status: str
    summary: str | None = None
    created_at: datetime
    logs: list[AgentLogOut] = []
    matches: list[MatchOut] = []
    insights: dict | None = None


# ---------- What-if simulator ----------
class SimulateRequest(ProfileBase):
    owned_documents: list[str] = []


class SimulateResponse(BaseModel):
    summary: str
    logs: list[AgentLogOut] = []
    matches: list[MatchOut] = []
    insights: dict


# ---------- Assistant ----------
class AssistantRequest(BaseModel):
    profile_id: int
    question: str = Field(min_length=1, max_length=500)


class AssistantResponse(BaseModel):
    answer: str
    grounded_on: int
