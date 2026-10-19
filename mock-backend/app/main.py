from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import SQLModel, Session, select
from .db import engine, get_session
from . import models, crud, auth, schemas
from .seed import create_initial_data
import os

app = FastAPI(title="Enterprise Recon - Backend")

# CORS for local UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    # seed admin user and sample exceptions if not present
    create_initial_data()


@app.post(API_PREFIX + "/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = crud.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token(subject=user.username, role=user.role)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get(API_PREFIX + "/reconciliation/exceptions")
def list_exceptions(status: str | None = None, limit: int = 50, current_user: models.User = Depends(auth.get_current_user)):
    with Session(engine) as session:
        q = select(models.Exception).order_by(models.Exception.created_at.desc()).limit(limit)
        if status:
            q = q.where(models.Exception.status == status)
        res = session.exec(q).all()
        return [schemas.ExceptionSummary.from_orm(r) for r in res]


@app.get(API_PREFIX + "/reconciliation/exceptions/{exc_id}")
def get_exception(exc_id: str, current_user: models.User = Depends(auth.get_current_user)):
    with Session(engine) as session:
        exc = session.get(models.Exception, exc_id)
        if not exc:
            raise HTTPException(status_code=404, detail="Exception not found")
        # load candidates and audit
        candidates = session.exec(select(models.Candidate).where(models.Candidate.exception_id == exc.id)).all()
        audit = session.exec(select(models.Audit).where(models.Audit.exception_id == exc.id).order_by(models.Audit.created_at.desc())).all()
        detail = schemas.ExceptionDetail.from_orm(exc)
        detail.candidates = [schemas.MatchCandidate.from_orm(c) for c in candidates]
        detail.audit = [schemas.AuditEntry.from_orm(a) for a in audit]
        return detail


@app.post(API_PREFIX + "/reconciliation/manual")
def manual_match(payload: schemas.ManualMatchRequest, current_user: models.User = Depends(auth.get_current_user)):
    # Only reviewers or admins can perform manual match
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="insufficient role")
    result = crud.apply_manual_action(payload, actor=current_user.username)
    return result


@app.get(API_PREFIX + "/reconciliation/summary")
def summary(current_user: models.User = Depends(auth.get_current_user)):
    with Session(engine) as session:
        open_count = session.exec(select(models.Exception).where(models.Exception.status == "open")).count()
        closed_count = session.exec(select(models.Exception).where(models.Exception.status == "closed")).count()
        return {
            "open": open_count,
            "closed": closed_count,
            "auto_matched_today": 3,
            "auto_match_rate": 0.72,
            "stale": open_count,
        }
