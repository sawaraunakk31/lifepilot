"""Profile CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session
import pypdf
import json

from typing import Optional
from app.database import get_db
from app import models, schemas
from app.llm.provider import get_provider
from app.auth import get_current_user

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=schemas.ProfileOut, status_code=201)
def create_profile(
    payload: schemas.ProfileCreate,
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    data = payload.model_dump()
    user_id = current_user.get("id") if current_user else None
    email = current_user.get("email") if current_user else None

    if user_id:
        data["user_id"] = user_id
        if not data.get("email") and email:
            data["email"] = email

    # Check if an existing profile already exists for this user to UPDATE it in Neon DB
    existing = None
    if user_id:
        from sqlalchemy import or_
        filters = [models.Profile.user_id == user_id]
        if email:
            filters.append(models.Profile.email == email)
        raw_name = data.get("name") or (current_user.get("name") if current_user else "")
        first_token = raw_name.split()[0] if raw_name else ""
        if first_token and len(first_token) >= 3:
            filters.append(models.Profile.name.ilike(f"%{first_token}%"))
        existing = db.scalars(
            select(models.Profile).where(or_(*filters)).order_by(models.Profile.created_at.desc())
        ).first()

    if existing:
        for k, v in data.items():
            if v is not None:
                setattr(existing, k, v)
        # Ensure strict 1-to-1: delete any duplicate stale profile rows for this user
        if user_id:
            db.query(models.Profile).filter(
                models.Profile.user_id == user_id,
                models.Profile.id != existing.id
            ).delete(synchronize_session=False)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # If inserting into an empty table or sequence is desynced, reset sequence to max(id)+1 (or 1)
        from sqlalchemy import text
        try:
            db.execute(text("SELECT setval(pg_get_serial_sequence('profiles', 'id'), COALESCE((SELECT MAX(id) FROM profiles), 0) + 1, false);"))
            db.commit()
        except Exception:
            pass

        profile = models.Profile(**data)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


@router.post("/parse-resume", response_model=schemas.ParseResumeResponse)
async def parse_resume(file: UploadFile = File(...)):
    """Parse a resume PDF and return extracted profile data."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    try:
        # Extract text using pypdf
        reader = pypdf.PdfReader(file.file)
        text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
            
        # Call LLM to parse
        llm = get_provider()
        prompt = f"""
        Extract the following profile information from the resume text below.
        Return ONLY a valid JSON object matching this schema, nothing else:
        {{
            "name": "Full Name",
            "email": "Email address",
            "age": 22, (estimate if possible, or null)
            "gender": "Male/Female/Other or null",
            "state": "State in India (e.g., Karnataka, Delhi) or null",
            "category": "General/OBC/SC/ST/EWS or null",
            "education_level": "Undergraduate/Postgraduate/High School etc.",
            "field_of_study": "e.g., Computer Science, Commerce",
            "annual_income": null,
            "disability": false,
            "goals": "Short summary of career goals based on resume"
        }}
        
        Resume Text:
        {text[:5000]}
        """
        
        # We use standard generate since this is an isolated task
        response = llm.generate(prompt, system="You are a strict JSON data extractor. Output only raw JSON.")
        
        # Clean JSON if wrapped in markdown
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned.replace("```json", "", 1).replace("```", "")
        elif cleaned.startswith("```"):
            cleaned = cleaned.replace("```", "", 2)
            
        data = json.loads(cleaned)
        return schemas.ParseResumeResponse(**data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {e}")


@router.get("/me/latest", response_model=Optional[schemas.ProfileOut])
def get_my_latest_profile(
    db: Session = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user),
):
    """Retrieve the latest saved citizen profile for the current authenticated user."""
    if not current_user or not current_user.get("id"):
        return None

    user_id = current_user["id"]
    email = current_user.get("email")
    from sqlalchemy import or_

    filters = [models.Profile.user_id == user_id]
    if email:
        filters.append(models.Profile.email == email)
    
    raw_name = current_user.get("name") or ""
    first_token = raw_name.split()[0] if raw_name else ""
    if first_token and len(first_token) >= 3:
        filters.append(models.Profile.name.ilike(f"%{first_token}%"))

    profile = db.scalars(
        select(models.Profile)
        .where(or_(*filters))
        .order_by(models.Profile.created_at.desc())
    ).first()

    # If this profile was legacy (user_id is null), automatically link it now!
    if profile and not profile.user_id:
        profile.user_id = user_id
        if email and not profile.email:
            profile.email = email
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
