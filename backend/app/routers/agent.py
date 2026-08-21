"""Agent run endpoints — triggers the multi-agent pipeline and serves results."""
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
    db.flush()

    for log in result["logs"]:
        db.add(models.AgentLog(run_id=run.id, agent=log["agent"],
                                message=log["message"],
                                confidence=log.get("confidence")))

    for m in result["matches"]:
        db.add(models.MatchResult(
            run_id=run.id,
            opportunity_id=m.get("opportunity_id", ""),
            title=m.get("title", ""),
            provider=m.get("provider"),
            url=m.get("url"),
            amount=m.get("amount"),
            deadline=m.get("deadline"),
            eligible=m.get("eligible", False),
            score=m.get("score", 0.0),
            confidence=m.get("confidence", 0.0),
            reasons=m.get("reasons", []),
            unmet=m.get("unmet", []),
            documents=m.get("documents", []),
            roadmap=m.get("roadmap", []),
        ))

    db.commit()
    db.refresh(run)

    out = schemas.AgentRunOut.model_validate(run)
    out.insights = result["insights"]
    return out


@router.post("/simulate", response_model=schemas.SimulateResponse)
def simulate(payload: schemas.SimulateRequest):
    """What-if simulator: evaluate an arbitrary profile WITHOUT saving."""
    data = payload.model_dump()
    owned = data.pop("owned_documents", [])
    profile = SimpleNamespace(**data, owned_documents=owned)
    result = Orchestrator().run(profile, owned_documents=owned)
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
    profile_dict = {
        "name": profile.name, "category": profile.category,
        "state": profile.state, "education_level": profile.education_level,
        "annual_income": profile.annual_income,
    }
    reply = assistant_service.answer(
        question=payload.question,
        matches=result["matches"],
        name=profile.name,
        profile_id=profile.id,
        profile=profile_dict,
    )
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
