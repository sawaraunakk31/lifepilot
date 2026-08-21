"""Profile CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=schemas.ProfileOut, status_code=201)
def create_profile(payload: schemas.ProfileCreate, db: Session = Depends(get_db)):
    profile = models.Profile(**payload.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=list[schemas.ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    return db.scalars(select(models.Profile).order_by(models.Profile.created_at.desc())).all()


@router.get("/{profile_id}", response_model=schemas.ProfileOut)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(models.Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.get(models.Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile)
    db.commit()
