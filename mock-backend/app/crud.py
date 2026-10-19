from .db import get_session
from .models import User, Exception, Candidate, Audit
from .auth import get_password_hash
from sqlmodel import Session, select
import time


def apply_manual_action(payload, actor: str):
    exc_id = payload.exception_id
    with Session(get_session().bind) as session:
        if not exc_id:
            # create new exception
            exc = Exception(exception_type="manual_action", reason=payload.note or "manual action", status=("closed" if payload.action=="match" else "open"), transaction_id=payload.transaction_id)
            session.add(exc)
            session.commit()
            session.refresh(exc)
            if payload.bank_settlement_id:
                cand = Candidate(exception_id=exc.id, bank_settlement_id=payload.bank_settlement_id, match_score=1.0)
                session.add(cand)
            audit = Audit(exception_id=exc.id, actor=actor, action=payload.action, note=payload.note)
            session.add(audit)
            session.commit()
            return {"ok": True, "exception_id": exc.id, "status": exc.status}
        else:
            exc = session.get(Exception, exc_id)
            if not exc:
                raise Exception("not found")
            # append audit
            audit = Audit(exception_id=exc.id, actor=actor, action=payload.action, note=payload.note)
            session.add(audit)
            if payload.action == "match":
                exc.status = "closed"
                if payload.bank_settlement_id:
                    cand = Candidate(exception_id=exc.id, bank_settlement_id=payload.bank_settlement_id, match_score=1.0)
                    session.add(cand)
            elif payload.action == "reject":
                exc.status = "open"
            session.add(exc)
            session.commit()
            return {"ok": True, "exception_id": exc.id, "status": exc.status}


def authenticate_user(username: str, password: str):
    with Session(get_session().bind) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if not user:
            return None
        from .auth import verify_password
        if not verify_password(password, user.hashed_password):
            return None
        return user
