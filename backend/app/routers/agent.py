"""Agent run endpoints - triggers the multi-agent pipeline and stores results."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.agents.orchestrator import Orchestrator
from app.services import assistant as assistant_service
from app.services import calendar as calendar_service

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/run/{profile_id}", response_model=schemas.AgentRunOut)
def run_agents(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(models.Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    result = Orchestrator().run(profile)

    run = models.AgentRun(profile_id=profile.id, status="completed", summary=result["summary"])
    db.add(run)
    db.flush()  # get run.id

    for log in result["logs"]:
        db.add(models.AgentLog(run_id=run.id, **log))

    for m in result["matches"]:
        db.add(models.MatchResult(run_id=run.id, **m))

    db.commit()
    db.refresh(run)

    out = schemas.AgentRunOut.model_validate(run)
    out.insights = result["insights"]
    return out


@router.post("/simulate", response_model=schemas.SimulateResponse)
def simulate(payload: schemas.SimulateRequest):
    """What-if simulator: evaluate an arbitrary profile WITHOUT saving anything."""
    data = payload.model_dump()
    owned = data.pop("owned_documents", [])
    profile = SimpleNamespace(**data, owned_documents=owned)
    result = Orchestrator().run(profile)
    return schemas.SimulateResponse(
        summary=result["summary"],
        logs=result["logs"],
        matches=result["matches"],
        insights=result["insights"],
    )


@router.post("/assistant", response_model=schemas.AssistantResponse)
def assistant(payload: schemas.AssistantRequest, db: Session = Depends(get_db)):
    profile = db.get(models.Profile, payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    result = Orchestrator().run(profile)
    reply = assistant_service.answer(payload.question, result["matches"], profile.name)
    return schemas.AssistantResponse(**reply)


@router.get("/calendar/{profile_id}")
def calendar(profile_id: int, db: Session = Depends(get_db)):
    """Download eligible-scheme deadlines as an .ics calendar file."""
    profile = db.get(models.Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    result = Orchestrator().run(profile)
    ics = calendar_service.build_ics(result["matches"], only_eligible=True)
    return Response(
        content=ics,
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=lifepilot-deadlines.ics"},
    )


@router.get("/runs/{profile_id}", response_model=list[schemas.AgentRunOut])
def list_runs(profile_id: int, db: Session = Depends(get_db)):
    runs = db.scalars(
        select(models.AgentRun)
        .where(models.AgentRun.profile_id == profile_id)
        .order_by(models.AgentRun.created_at.desc())
    ).all()
    return runs


@router.get("/run/{run_id}", response_model=schemas.AgentRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(models.AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
