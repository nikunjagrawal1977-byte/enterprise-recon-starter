from .db import engine
from .models import User, Exception, Candidate, Audit
from .auth import get_password_hash, verify_password
from sqlmodel import Session, select


def apply_manual_action(payload, actor: str):
    with Session(engine) as session:
        exc_id = payload.exception_id
        if not exc_id:
            exc = Exception(
                exception_type="manual_action",
                reason=payload.note or "manual action",
                status="closed" if payload.action == "match" else "open",
                transaction_id=payload.transaction_id,
            )
            session.add(exc)
            session.commit()
            session.refresh(exc)
            if payload.bank_settlement_id:
                session.add(Candidate(exception_id=exc.id, bank_settlement_id=payload.bank_settlement_id, match_score=1.0))
            session.add(Audit(exception_id=exc.id, actor=actor, action=payload.action, note=payload.note))
            session.commit()
            return {"ok": True, "exception_id": exc.id, "status": exc.status}

        exc = session.get(Exception, exc_id)
        if not exc:
            raise Exception("exception not found")
        session.add(Audit(exception_id=exc.id, actor=actor, action=payload.action, note=payload.note))
        if payload.action == "match":
            exc.status = "closed"
            if payload.bank_settlement_id:
                session.add(Candidate(exception_id=exc.id, bank_settlement_id=payload.bank_settlement_id, match_score=1.0))
        elif payload.action == "reject":
            exc.status = "open"
        session.add(exc)
        session.commit()
        return {"ok": True, "exception_id": exc.id, "status": exc.status}


def authenticate_user(username: str, password: str):
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
