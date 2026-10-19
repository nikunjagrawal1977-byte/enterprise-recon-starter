from sqlmodel import Session, select
from .db import engine
from .models import User, Exception, Candidate, Audit, Account, FxRate
from .auth import get_password_hash


def create_initial_data():
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == "admin")).first() is None:
            session.add(User(username="admin", hashed_password=get_password_hash("adminpass"), role="admin"))
        if session.exec(select(User).where(User.username == "reviewer")).first() is None:
            session.add(User(username="reviewer", hashed_password=get_password_hash("reviewerpass"), role="reviewer"))

        account_codes = {
            "bank_cash_inr": "Bank Cash - INR",
            "gateway_clearing_inr": "Gateway Clearing - INR",
            "merchant_revenue_inr": "Merchant Revenue - INR",
            "gateway_fees_inr": "Gateway Fee - INR",
            "tax_payable_inr": "Tax Payable - INR",
            "suspense_inr": "Suspense - INR",
        }
        for code, name in account_codes.items():
            if session.exec(select(Account).where(Account.account_code == code)).first() is None:
                session.add(Account(account_code=code, account_name=name, account_type="merchant" if "revenue" in code else "bank" if "bank" in code else "fees" if "fee" in code else "tax" if "tax" in code else "suspense" if "suspense" in code else "clearing", currency="INR"))

        if session.exec(select(FxRate).where(FxRate.quote_currency == "USD")).first() is None:
            session.add(FxRate(base_currency="INR", quote_currency="USD", rate=0.012, valid_from=None))

        if session.exec(select(Exception)).first() is None:
            exc = Exception(exception_type="unmatched_deposit", reason="Seeded unmatched deposit", amount=2500.0, priority="high", status="open", transaction_id="txn-pay_123")
            session.add(exc)
            session.commit()
            session.refresh(exc)
            session.add(Candidate(exception_id=exc.id, bank_settlement_id="bank-settle-001", amount=2500.0, payment_ts=1700000000, payment_method="upi", bank_ref="UTR123456", match_score=0.94))
            session.add(Audit(exception_id=exc.id, actor="system", action="created", note=None))

        session.commit()
