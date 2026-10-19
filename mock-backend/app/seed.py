from .db import get_session
from .models import User, Exception, Candidate, Audit
from .auth import get_password_hash
from sqlmodel import Session, select


def create_initial_data():
    with Session(get_session().bind) as session:
        # create admin if not exists
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if not admin:
            u = User(username="admin", hashed_password=get_password_hash("adminpass"), role="admin")
            session.add(u)
        reviewer = session.exec(select(User).where(User.username == "reviewer")).first()
        if not reviewer:
            r = User(username="reviewer", hashed_password=get_password_hash("reviewerpass"), role="reviewer")
            session.add(r)
        session.commit()
        # seed one exception if none exist
        ex = session.exec(select(Exception)).first()
        if not ex:
            e = Exception(exception_type="unmatched_deposit", reason="Seeded unmatched deposit", amount=2500.0, priority="high", status="open", transaction_id="txn-pay_123")
            session.add(e)
            session.commit()
            session.refresh(e)
            c = Candidate(exception_id=e.id, bank_settlement_id="bank-settle-001", amount=2500.0, payment_ts=None, payment_method="upi", bank_ref="UTR123456", match_score=0.94)
            session.add(c)
            a = Audit(exception_id=e.id, actor="system", action="created", note=None)
            session.add(a)
            session.commit()
