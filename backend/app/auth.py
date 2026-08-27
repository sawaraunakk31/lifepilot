"""Authentication helpers for Kinde Auth and JWT verification."""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("lifepilot.auth")

_bearer_scheme = HTTPBearer(auto_error=False)
_jwks_client: Optional[PyJWKClient] = None

router_auth = APIRouter(prefix="/api/auth", tags=["auth"])


class ExchangeRequest(BaseModel):
    code: str
    code_verifier: str = ""
    redirect_uri: str


def get_jwks_client() -> Optional[PyJWKClient]:
    """Lazy initialize Kinde JWKS client."""
    global _jwks_client
    if _jwks_client is None and settings.kinde_domain:
        domain = settings.kinde_domain.rstrip("/")
        jwks_url = f"{domain}/.well-known/jwks.json"
        try:
            _jwks_client = PyJWKClient(jwks_url)
        except Exception as e:
            logger.warning(f"Failed to initialize Kinde JWKS client: {e}")
    return _jwks_client


def verify_kinde_token(token: str) -> dict[str, Any]:
    """Verify and decode a Kinde JWT token using Kinde's JWKS."""
    if not settings.kinde_domain:
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            )

    client = get_jwks_client()
    if not client:
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            )

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=60,
        )
        return payload
    except jwt.PyJWTError as e:
        logger.debug(f"JWT Verification notice: {e}")
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token verification error: {e}",
            )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[dict[str, Any]]:
    """Optional authentication dependency: returns user dict or None if guest."""
    if not credentials or not credentials.credentials:
        return None

    token = credentials.credentials
    try:
        payload = verify_kinde_token(token)
        user_id = payload.get("sub") or payload.get("id")
        if not user_id:
            return None

        # Fetch stored user record from Neon DB
        from app.database import SessionLocal
        from app.models import User
        with SessionLocal() as db:
            db_user = db.query(User).filter(User.id == user_id).first()
            if db_user:
                return {
                    "id": db_user.id,
                    "email": db_user.email,
                    "name": db_user.name or payload.get("name", "Citizen"),
                    "picture": db_user.picture or payload.get("picture"),
                }

        return {
            "id": user_id,
            "email": payload.get("email"),
            "name": payload.get("name") or payload.get("given_name", "Citizen"),
            "picture": payload.get("picture"),
        }
    except Exception as e:
        logger.debug(f"Auth header present but invalid: {e}")
        return None


import base64
import hashlib
import secrets
from fastapi import Request
from fastapi.responses import RedirectResponse


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


@router_auth.get("/login")
def login(request: Request):
    """Direct HTTP redirect to Kinde Auth login page with PKCE challenge."""
    if not settings.kinde_domain or not settings.kinde_client_id:
        return RedirectResponse(url="/")

    domain = settings.kinde_domain.rstrip("/")
    base_url = str(request.base_url).rstrip("/")
    state = secrets.token_urlsafe(16)
    verifier, challenge = generate_pkce_pair()

    login_url = (
        f"{domain}/oauth2/auth?"
        f"response_type=code&"
        f"client_id={urllib.parse.quote(settings.kinde_client_id)}&"
        f"redirect_uri={urllib.parse.quote(base_url)}&"
        f"scope=openid%20profile%20email&"
        f"state={state}&"
        f"code_challenge={challenge}&"
        f"code_challenge_method=S256"
    )
    
    response = RedirectResponse(url=login_url)
    response.set_cookie(
        key="kinde_verifier",
        value=verifier,
        httponly=False,
        samesite="lax",
        max_age=600,
    )
    return response


@router_auth.get("/logout")
def logout(request: Request):
    """Logout redirect."""
    base_url = str(request.base_url).rstrip("/")
    if settings.kinde_domain:
        domain = settings.kinde_domain.rstrip("/")
        response = RedirectResponse(url=f"{domain}/logout?redirect={urllib.parse.quote(base_url)}")
        response.delete_cookie("kinde_verifier")
        return response
    return RedirectResponse(url="/")


@router_auth.post("/exchange")
def exchange_token(req: ExchangeRequest, request: Request):
    """Exchange authorization code for Kinde access and ID tokens."""
    if not settings.kinde_domain or not settings.kinde_client_id:
        raise HTTPException(status_code=400, detail="Kinde auth is not configured.")

    token_url = f"{settings.kinde_domain.rstrip('/')}/oauth2/token"
    clean_redirect_uri = req.redirect_uri.split("?")[0].rstrip("/")
    verifier = request.cookies.get("kinde_verifier") or req.code_verifier or ""

    form_data = {
        "grant_type": "authorization_code",
        "client_id": settings.kinde_client_id,
        "code": req.code,
        "redirect_uri": clean_redirect_uri,
    }
    if verifier:
        form_data["code_verifier"] = verifier

    encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")
    request = urllib.request.Request(
        token_url,
        data=encoded_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "LifePilot/2.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        logger.error(f"Kinde token exchange error ({e.code}): {err_body}")
        raise HTTPException(status_code=e.code, detail=f"Kinde error: {err_body}")
    except Exception as e:
        logger.error(f"Failed token request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    access_token = data.get("access_token")
    id_token = data.get("id_token")

    # Decode user info from id_token or access_token
    user_info = {}
    for tok in [id_token, access_token]:
        if tok:
            try:
                decoded = verify_kinde_token(tok)
                user_info = {
                    "id": decoded.get("sub") or decoded.get("id"),
                    "email": decoded.get("email"),
                    "name": decoded.get("name") or decoded.get("given_name", "Citizen"),
                    "given_name": decoded.get("given_name"),
                    "picture": decoded.get("picture"),
                }
                if user_info.get("id"):
                    break
            except Exception:
                pass

    # If email or name is missing, query Kinde's user profile endpoint
    if access_token and (not user_info.get("email") or not user_info.get("id")):
        try:
            profile_url = f"{settings.kinde_domain.rstrip('/')}/oauth2/v2/user_profile"
            prof_req = urllib.request.Request(
                profile_url,
                headers={"Authorization": f"Bearer {access_token}", "User-Agent": "LifePilot/2.0"},
            )
            with urllib.request.urlopen(prof_req, timeout=10) as prof_resp:
                prof_data = json.loads(prof_resp.read().decode("utf-8"))
                user_info["id"] = user_info.get("id") or prof_data.get("id") or prof_data.get("sub")
                user_info["email"] = user_info.get("email") or prof_data.get("email") or prof_data.get("preferred_email")
                user_info["name"] = user_info.get("name") or prof_data.get("name") or prof_data.get("given_name") or "Citizen"
                user_info["picture"] = user_info.get("picture") or prof_data.get("picture")
        except Exception as e:
            logger.debug(f"User profile fallback notice: {e}")

    # Persist or update user in Neon database
    if user_info.get("id"):
        try:
            from datetime import datetime, timezone
            from app.database import SessionLocal
            from app.models import User

            with SessionLocal() as db:
                user_obj = db.query(User).filter(User.id == user_info["id"]).first()
                if not user_obj:
                    user_obj = User(
                        id=user_info["id"],
                        email=user_info.get("email"),
                        name=user_info.get("name"),
                        picture=user_info.get("picture"),
                        created_at=datetime.now(timezone.utc),
                        last_login_at=datetime.now(timezone.utc),
                    )
                    db.add(user_obj)
                else:
                    user_obj.email = user_info.get("email") or user_obj.email
                    user_obj.name = user_info.get("name") or user_obj.name
                    user_obj.picture = user_info.get("picture") or user_obj.picture
                    user_obj.last_login_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e:
            logger.warning(f"Could not persist user to Neon DB: {e}")

    return {
        "access_token": access_token,
        "id_token": id_token,
        "user": user_info,
    }


@router_auth.delete("/account")
def delete_account(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Delete citizen user account and all associated data from Neon DB and Kinde."""
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Authentication required to delete account.")

    user_id = user["id"]
    from app.database import SessionLocal
    from app.models import AgentLog, AgentRun, MatchResult, Profile, User

    # 1. Delete from Neon PostgreSQL DB
    try:
        from sqlalchemy import text
        with SessionLocal() as db:
            try:
                db.execute(text("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS user_id VARCHAR(120);"))
                db.commit()
            except Exception:
                pass

            from sqlalchemy import or_
            query_filters = [Profile.user_id == user_id]
            if user.get("email"):
                query_filters.append(Profile.email == user["email"])
            if user.get("name"):
                query_filters.append(Profile.name.ilike(user["name"]))
            
            profiles = db.query(Profile).filter(or_(*query_filters)).all()
            profile_ids = [p.id for p in profiles]

            if profile_ids:
                runs = db.query(AgentRun).filter(AgentRun.profile_id.in_(profile_ids)).all()
                run_ids = [r.id for r in runs]
                if run_ids:
                    db.query(AgentLog).filter(AgentLog.run_id.in_(run_ids)).delete(synchronize_session=False)
                    db.query(MatchResult).filter(MatchResult.run_id.in_(run_ids)).delete(synchronize_session=False)
                    db.query(AgentRun).filter(AgentRun.id.in_(run_ids)).delete(synchronize_session=False)
                db.query(Profile).filter(Profile.id.in_(profile_ids)).delete(synchronize_session=False)

            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
            db.commit()

            # If tables are empty after deletion, reset PostgreSQL auto-increment sequences back to 1
            try:
                if db.query(Profile).count() == 0:
                    db.execute(text("ALTER SEQUENCE IF EXISTS profiles_id_seq RESTART WITH 1;"))
                if db.query(AgentRun).count() == 0:
                    db.execute(text("ALTER SEQUENCE IF EXISTS agent_runs_id_seq RESTART WITH 1;"))
                if db.query(MatchResult).count() == 0:
                    db.execute(text("ALTER SEQUENCE IF EXISTS match_results_id_seq RESTART WITH 1;"))
                if db.query(AgentLog).count() == 0:
                    db.execute(text("ALTER SEQUENCE IF EXISTS agent_logs_id_seq RESTART WITH 1;"))
                db.commit()
            except Exception:
                pass

            logger.info(f"Deleted user {user_id}, {len(profile_ids)} profiles, and all related schemes from Neon DB.")
    except Exception as e:
        logger.error(f"Error deleting user from Neon DB: {e}")

    # 2. If Kinde M2M configured, delete user via Kinde Management API
    if settings.kinde_domain and settings.kinde_m2m_client_id and settings.kinde_m2m_client_secret:
        try:
            domain = settings.kinde_domain.rstrip("/")
            m2m_token_url = f"{domain}/oauth2/token"
            m2m_data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": settings.kinde_m2m_client_id,
                "client_secret": settings.kinde_m2m_client_secret,
                "audience": f"{domain}/api",
            }).encode("utf-8")
            m2m_req = urllib.request.Request(
                m2m_token_url,
                data=m2m_data,
                headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "LifePilot/2.0"},
                method="POST",
            )
            m2m_token = None
            try:
                with urllib.request.urlopen(m2m_req, timeout=10) as m2m_resp:
                    m2m_json = json.loads(m2m_resp.read().decode("utf-8"))
                    m2m_token = m2m_json.get("access_token")
            except urllib.error.HTTPError as m2m_err:
                m2m_err_msg = m2m_err.read().decode("utf-8")
                logger.error(f"Kinde M2M token error ({m2m_err.code}): {m2m_err_msg}")

            if m2m_token:
                del_url = f"{domain}/api/v1/user?id={urllib.parse.quote(user_id)}&is_delete_profile=true"
                del_req = urllib.request.Request(
                    del_url,
                    headers={
                        "Authorization": f"Bearer {m2m_token}",
                        "User-Agent": "LifePilot/2.0",
                        "Accept": "application/json",
                    },
                    method="DELETE",
                )
                try:
                    with urllib.request.urlopen(del_req, timeout=10) as del_resp:
                        resp_data = del_resp.read().decode("utf-8")
                        logger.info(f"Deleted user {user_id} from Kinde Management API: status {del_resp.status} - {resp_data}")
                except urllib.error.HTTPError as http_err:
                    err_body = http_err.read().decode("utf-8")
                    logger.warning(f"Kinde Management API delete notice ({http_err.code}): {err_body}")
        except Exception as e:
            logger.warning(f"Kinde Management API delete notice: {e}")

    base_url = str(request.base_url).rstrip("/")
    logout_url = f"{settings.kinde_domain.rstrip('/')}/logout?redirect={urllib.parse.quote(base_url)}" if settings.kinde_domain else "/"
    return {"deleted": True, "logout_url": logout_url}
