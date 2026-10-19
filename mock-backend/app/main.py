from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import SQLModel, Session, select
from .db import engine, get_session
from . import models, crud, auth, schemas, ledger, reconcile
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
    # Ensure models exist for local/dev; migrations are preferred for prod
    try:
        SQLModel.metadata.create_all(engine)
    except Exception:
        # ignore if DB not ready; migrations should be used in prod
        pass
    # seed admin user and sample exceptions if not present
    try:
        create_initial_data()
    except Exception:
        pass


@app.post(API_PREFIX + "/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = crud.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    access_token = auth.create_access_token(subject=user.username, role=user.role)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post(API_PREFIX + "/transactions")
def ingest_transaction(payload: dict, current_user: models.User = Depends(auth.get_current_user)):
    """Ingest a canonical payment transaction (any channel) and create ledger postings."""
    try:
        res = ledger.create_payment_transaction(payload)
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(API_PREFIX + "/bank_lines")
def ingest_bank_line(payload: dict, current_user: models.User = Depends(auth.get_current_user)):
    """Ingest a bank statement line and create settlement journal."""
    try:
        res = ledger.create_bank_statement_line(payload)
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(API_PREFIX + "/reconciliation/reconcile")
def reconcile_endpoint(payload: dict, current_user: models.User = Depends(auth.get_current_user)):
    """Attempt to reconcile a payment transaction to a bank statement line."""
    try:
        res = ledger.reconcile_transaction(payload)
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(API_PREFIX + "/ledger/trial_balance")
def trial_balance(current_user: models.User = Depends(auth.get_current_user)):
    try:
        res = ledger.get_trial_balance()
        return {"ok": True, "trial_balance": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


# --- New reconciliation endpoints ---

@app.get(API_PREFIX + "/reconciliation/candidates/{txn_id}")
def get_candidates(txn_id: str, current_user: models.User = Depends(auth.get_current_user)):
    """Return candidate bank lines for a transaction and persist them for review."""
    with Session(engine) as session:
        txn = session.exec(select(models.PaymentTransaction).where(models.PaymentTransaction.id == txn_id)).first()
        if not txn:
            txn = session.exec(select(models.PaymentTransaction).where(models.PaymentTransaction.source_txn_id == txn_id)).first()
        if not txn:
            raise HTTPException(status_code=404, detail="transaction not found")
        candidates = reconcile.generate_candidates_for_txn(txn, session)
        # persist candidates into Candidate table for UI review
        from .models import Candidate
        persisted = []
        for c in candidates:
            # check if candidate already exists
            existing = session.exec(select(Candidate).where(Candidate.gateway_txn_id == txn.source_txn_id).where(Candidate.bank_settlement_id == c['bank_statement_line_id'])).first()
            if existing:
                persisted.append({"id": existing.id, "score": c['score']})
                continue
            cand = Candidate(id=str(uuid4()), exception_id=None, bank_settlement_id=c['bank_statement_line_id'], gateway_txn_id=txn.source_txn_id, amount=c['amount'], payment_ts=None, payment_method=txn.payment_method, bank_ref=txn.bank_ref, match_score=c['score'])
            session.add(cand)
            session.commit()
            session.refresh(cand)
            persisted.append({"id": cand.id, "score": c['score']})
        return {"txn_id": txn.id, "candidates": candidates, "persisted": persisted}


@app.post(API_PREFIX + "/reconciliation/auto-run")
def auto_run(current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="insufficient role")
    stats = reconcile.run_auto_reconcile()
    return {"ok": True, "stats": stats}


@app.post(API_PREFIX + "/reconciliation/force-match")
def force_match(payload: dict, current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="insufficient role")
    payment_id = payload.get("payment_transaction_id")
    bank_id = payload.get("bank_statement_line_id")
    actor = current_user.username
    try:
        res = reconcile.force_match(payment_id, bank_id, actor=actor)
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(API_PREFIX + "/reconciliation/reject")
def reject_candidate(payload: dict, current_user: models.User = Depends(auth.get_current_user)):
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="insufficient role")
    payment_id = payload.get("payment_transaction_id")
    bank_id = payload.get("bank_statement_line_id")
    actor = current_user.username
    try:
        res = reconcile.reject_candidate(payment_id, bank_id, actor=actor)
        return {"ok": True, "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get(API_PREFIX + "/reconciliation/unmatched")
def unmatched(current_user: models.User = Depends(auth.get_current_user), limit: int = 100, offset: int = 0):
    if current_user.role not in ("reviewer", "admin"):
        raise HTTPException(status_code=403, detail="insufficient role")
    res = reconcile.list_unmatched_payments(limit=limit, offset=offset)
    return {"ok": True, "unmatched": res}
