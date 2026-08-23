"""Profile CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session
import pypdf
import json

from app.database import get_db
from app import models, schemas
from app.llm.provider import get_provider

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.post("", response_model=schemas.ProfileOut, status_code=201)
def create_profile(payload: schemas.ProfileCreate, db: Session = Depends(get_db)):
    profile = models.Profile(**payload.model_dump())
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
        
        # We use standard chat since this is an isolated task
        response = llm.chat(prompt, system_prompt="You are a strict JSON data extractor. Output only raw JSON.")
        
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
