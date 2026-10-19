import os
from typing import List, Dict, Any
from uuid import uuid4
from datetime import datetime
from sqlmodel import Session, select

from .db import engine
from .models import PaymentTransaction, BankStatementLine, Reconciliation, Candidate, Audit

AUTO_MATCH_THRESHOLD = float(os.environ.get("AUTO_MATCH_THRESHOLD", "0.88"))


def score_candidate(txn: PaymentTransaction, bank_line: BankStatementLine) -> float:
    """Compute a heuristic score between 0 and 1 for matching a payment txn to a bank line."""
    score = 0.0

    # Exact UTR or statement_ref match => very high
    if bank_line.utr and txn.utr and bank_line.utr == txn.utr:
        score += 0.6

    # bank_ref or statement_ref vs txn.bank_ref
    if bank_line.statement_ref and txn.bank_ref and bank_line.statement_ref == txn.bank_ref:
        score += 0.5

    # Amount similarity (normalized)
    try:
        amt_txn = float(txn.amount)
        amt_bank = float(bank_line.amount)
        if amt_txn > 0:
            diff = abs(amt_txn - amt_bank)
            amt_score = max(0.0, 1.0 - (diff / max(amt_txn, 1.0))) * 0.4
            score += amt_score
    except Exception:
        pass

    # Time proximity (if dates available)
    try:
        # txn.payment_time may be datetime or number; bank_line.entry_date is datetime
        txn_time = txn.payment_time
        if isinstance(txn_time, (int, float)):
            txn_dt = datetime.utcfromtimestamp(txn_time)
        else:
            txn_dt = txn.payment_time
        if txn_dt and bank_line.entry_date:
            delta_days = abs((bank_line.entry_date - txn_dt).total_seconds()) / (3600 * 24)
            # within 1 day: bonus, within 7 days small bonus
            if delta_days <= 1:
                score += 0.1
            elif delta_days <= 7:
                score += 0.03
    except Exception:
        pass

    # Cap score to 1.0
    return min(score, 1.0)


def generate_candidates_for_txn(txn: PaymentTransaction, session: Session, max_candidates: int = 10) -> List[Dict[str, Any]]:
    """Find possible bank lines that could match the given txn.
    Strategy: find bank lines within +/- 5% amount or exact UTR/statement_ref matches, order by score.
    """
    candidates = []

    # first, try exact UTR or statement_ref matches
    if txn.utr:
        q = select(BankStatementLine).where(BankStatementLine.utr == txn.utr)
        for bl in session.exec(q).all():
            s = score_candidate(txn, bl)
            candidates.append((s, bl))

    if txn.bank_ref:
        q = select(BankStatementLine).where(BankStatementLine.statement_ref == txn.bank_ref)
        for bl in session.exec(q).all():
            s = score_candidate(txn, bl)
            candidates.append((s, bl))

    # broaden search by amount proximity (5% tolerance)
    try:
        amt = float(txn.amount)
        lower = amt * 0.95
        upper = amt * 1.05
        q = select(BankStatementLine).where(BankStatementLine.amount >= lower).where(BankStatementLine.amount <= upper)
        for bl in session.exec(q).all():
            s = score_candidate(txn, bl)
            candidates.append((s, bl))
    except Exception:
        pass

    # Deduplicate by id, keep highest score
    best = {}
    for s, bl in candidates:
        prev = best.get(bl.id)
        if not prev or s > prev[0]:
            best[bl.id] = (s, bl)

    ranked = sorted(best.values(), key=lambda x: x[0], reverse=True)
    results = []
    for s, bl in ranked[:max_candidates]:
        results.append({
            "bank_statement_line_id": bl.id,
            "statement_ref": bl.statement_ref,
            "utr": bl.utr,
            "amount": bl.amount,
            "currency": bl.currency,
            "entry_date": bl.entry_date.isoformat() if bl.entry_date else None,
            "score": round(s, 4),
            "narration": bl.narration,
        })
    return results


def generate_and_persist_candidates(txn_id: str, session: Session, max_candidates: int = 10) -> List[Dict[str, Any]]:
    txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.id == txn_id)).first()
    if not txn:
        txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.source_txn_id == txn_id)).first()
    if not txn:
        raise ValueError("transaction not found")
    candidates = generate_candidates_for_txn(txn, session, max_candidates=max_candidates)
    persisted = []
    for c in candidates:
        existing = session.exec(select(Candidate).where(Candidate.gateway_txn_id == txn.source_txn_id).where(Candidate.bank_settlement_id == c['bank_statement_line_id'])).first()
        if existing:
            persisted.append({"id": existing.id, "score": c['score']})
            continue
        cand = Candidate(id=str(uuid4()), exception_id=None, bank_settlement_id=c['bank_statement_line_id'], gateway_txn_id=txn.source_txn_id, amount=c['amount'], payment_ts=None, payment_method=txn.payment_method, bank_ref=txn.bank_ref, match_score=c['score'])
        session.add(cand)
        session.commit()
        session.refresh(cand)
        persisted.append({"id": cand.id, "score": c['score']})
    return persisted


def force_match(payment_id: str, bank_line_id: str, actor: str | None = None) -> Dict[str, Any]:
    with Session(engine) as session:
        txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.id == payment_id)).first()
        if not txn:
            txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.source_txn_id == payment_id)).first()
        if not txn:
            raise ValueError("payment transaction not found")
        bl = session.get(BankStatementLine, bank_line_id)
        if not bl:
            raise ValueError("bank statement line not found")

        # create reconciliation record
        rec = Reconciliation(id=str(uuid4()), source_type="payment", source_id=txn.id, payment_transaction_id=txn.id, bank_statement_line_id=bl.id, match_score=1.0, rule_applied="force_match", status="matched", notes=f"force matched by {actor or 'system'}")
        session.add(rec)
        txn.status = "reconciled"
        bl.status = "matched"
        session.add(txn)
        session.add(bl)
        # add audit
        audit = Audit(id=str(uuid4()), exception_id=None, actor=actor or "system", action="force_match", note=f"forced match: {txn.id} <-> {bl.id}")
        session.add(audit)
        session.commit()
        return {"reconciliation_id": rec.id, "matched": True}


def reject_candidate(payment_id: str, bank_line_id: str, actor: str | None = None) -> Dict[str, Any]:
    with Session(engine) as session:
        txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.id == payment_id)).first()
        if not txn:
            txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.source_txn_id == payment_id)).first()
        if not txn:
            raise ValueError("payment transaction not found")
        bl = session.get(BankStatementLine, bank_line_id)
        if not bl:
            raise ValueError("bank statement line not found")

        rec = Reconciliation(id=str(uuid4()), source_type="payment", source_id=txn.id, payment_transaction_id=txn.id, bank_statement_line_id=bl.id, match_score=0.0, rule_applied="manual_reject", status="rejected", notes=f"rejected by {actor or 'system'}")
        session.add(rec)
        # create an exception for manual review
        from .models import Exception as ExceptionModel
        exc = ExceptionModel(id=str(uuid4()), exception_type="rejected_candidate", reason="manual rejection of candidate", amount=txn.amount, transaction_id=txn.id)
        session.add(exc)
        # link a candidate record to the exception
        cand = Candidate(id=str(uuid4()), exception_id=exc.id, bank_settlement_id=bl.id, gateway_txn_id=txn.source_txn_id, amount=txn.amount, payment_ts=None, payment_method=txn.payment_method, bank_ref=txn.bank_ref, match_score=0.0)
        session.add(cand)
        # audit
        audit = Audit(id=str(uuid4()), exception_id=exc.id, actor=actor or "system", action="reject", note=f"rejected candidate for txn {txn.id} and bank line {bl.id}")
        session.add(audit)
        session.commit()
        return {"reconciliation_id": rec.id, "exception_id": exc.id, "rejected": True}


def run_auto_reconcile(limit: int = 1000) -> Dict[str, Any]:
    # keep existing run_auto_reconcile but delegate to earlier function to avoid duplication
    from .reconcile import run_auto_reconcile as _run
    return _run(limit=limit)


def list_unmatched_payments(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    from .reconcile import list_unmatched_payments as _list
    return _list(limit=limit, offset=offset)
