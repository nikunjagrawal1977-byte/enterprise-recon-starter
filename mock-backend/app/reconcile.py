import os
from typing import List, Dict, Any
from uuid import uuid4
from datetime import datetime
from sqlmodel import Session, select

from .db import engine
from .models import PaymentTransaction, BankStatementLine, Reconciliation


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
        delta_days = abs((bank_line.entry_date - txn.payment_time).total_seconds()) / (3600 * 24)
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


def run_auto_reconcile(limit: int = 1000) -> Dict[str, Any]:
    """Attempt to auto-reconcile open payments up to `limit` transactions.
    Returns statistics about attempts and matches created.
    """
    stats = {"processed": 0, "matched": 0, "open": 0}
    with Session(engine) as session:
        # find transactions that are not yet reconciled (no Reconciliation with status matched)
        subq = select(Reconciliation.payment_transaction_id).where(Reconciliation.status == "matched")
        q = select(PaymentTransaction).where(PaymentTransaction.status != "reconciled")
        txns = session.exec(q.limit(limit)).all()
        for txn in txns:
            stats["processed"] += 1
            candidates = generate_candidates_for_txn(txn, session)
            if not candidates:
                # create Reconciliation record with open status referencing txn only
                rec = Reconciliation(id=str(uuid4()), source_type="payment", source_id=txn.id, payment_transaction_id=txn.id, match_score=0.0, rule_applied="none", status="open", notes="no candidates")
                session.add(rec)
                session.commit()
                stats["open"] += 1
                continue

            top = candidates[0]
            score = float(top["score"])
            bank_line_id = top["bank_statement_line_id"]
            status = "matched" if score >= AUTO_MATCH_THRESHOLD else "open"
            rec = Reconciliation(id=str(uuid4()), source_type="payment", source_id=txn.id, payment_transaction_id=txn.id, bank_statement_line_id=bank_line_id, match_score=score, rule_applied="auto_amount_ref", status=status, notes=f"auto:top_score={score}")
            session.add(rec)
            if status == "matched":
                # mark txn as reconciled (simple status change) and bank line as matched
                txn.status = "reconciled"
                bl = session.get(BankStatementLine, bank_line_id)
                if bl:
                    bl.status = "matched"
                    session.add(bl)
                stats["matched"] += 1
            else:
                stats["open"] += 1
            session.add(txn)
            session.commit()
    return stats


def list_unmatched_payments(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    with Session(engine) as session:
        # payments that do not have a matched reconciliation
        subq = select(Reconciliation.payment_transaction_id).where(Reconciliation.status == "matched")
        q = select(PaymentTransaction).where(PaymentTransaction.id.notin_(subq)).limit(limit).offset(offset)
        res = []
        for txn in session.exec(q).all():
            res.append({
                "id": txn.id,
                "source": txn.source,
                "source_txn_id": txn.source_txn_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "status": txn.status,
            })
        return res
