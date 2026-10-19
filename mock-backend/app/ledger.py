from __future__ import annotations
from uuid import uuid4
from typing import Any, Dict, List
from sqlmodel import Session, select

from .db import engine
from .models import Account, BankStatementLine, JournalEntry, PaymentTransaction, Posting, Reconciliation


def get_or_create_account(session: Session, code: str, name: str, account_type: str = "merchant", currency: str = "INR") -> Account:
    account = session.exec(select(Account).where(Account.account_code == code)).first()
    if account:
        return account
    account = Account(id=str(uuid4()), account_code=code, account_name=name, account_type=account_type, currency=currency)
    session.add(account)
    session.commit()
    session.refresh(account)
    return account


def _create_postings_for_journal(session: Session, journal_entry: JournalEntry, postings: List[Dict[str, Any]]) -> None:
    debit_total = sum(float(p["amount"]) for p in postings if p["debit_credit"] == "debit")
    credit_total = sum(float(p["amount"]) for p in postings if p["debit_credit"] == "credit")
    if abs(debit_total - credit_total) > 0.01:
        raise ValueError(f"Journal {journal_entry.entry_no} is out of balance: debit_total={debit_total}, credit_total={credit_total}")

    for item in postings:
        acc = get_or_create_account(session, item["account_code"], item["account_name"], item.get("account_type", "merchant"), item.get("currency", "INR"))
        posting = Posting(
            id=str(uuid4()),
            journal_entry_id=journal_entry.id,
            account_id=acc.id,
            amount=float(item["amount"]),
            currency=item.get("currency", "INR"),
            debit_credit=item["debit_credit"],
        )
        session.add(posting)


def create_payment_transaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    source_txn_id = payload.get("source_txn_id") or payload.get("gateway_txn_id") or payload.get("id")
    if not source_txn_id:
        raise ValueError("source_txn_id is required")

    with Session(engine) as session:
        existing = session.exec(select(PaymentTransaction).where(PaymentTransaction.source_txn_id == source_txn_id)).first()
        if existing:
            existing.source = payload.get("source", existing.source)
            existing.source_txn_id = source_txn_id
            existing.merchant_txn_id = payload.get("merchant_txn_id") or existing.merchant_txn_id
            existing.payment_method = payload.get("payment_method") or existing.payment_method
            existing.amount = float(payload.get("amount") or existing.amount)
            existing.currency = payload.get("currency") or existing.currency
            existing.fees = float(payload.get("fees") or existing.fees)
            existing.net_amount = float(payload.get("net_amount") or (existing.amount - existing.fees))
            existing.status = payload.get("status") or existing.status
            existing.settlement_batch_id = payload.get("settlement_batch_id") or existing.settlement_batch_id
            existing.bank_ref = payload.get("bank_ref") or existing.bank_ref
            existing.utr = payload.get("utr") or existing.utr
            txn = existing
        else:
            txn = PaymentTransaction(
                id=str(uuid4()),
                source=payload.get("source", "razorpay"),
                source_txn_id=source_txn_id,
                merchant_txn_id=payload.get("merchant_txn_id"),
                payment_method=payload.get("payment_method", "card"),
                amount=float(payload.get("amount") or 0.0),
                currency=payload.get("currency") or "INR",
                fees=float(payload.get("fees") or 0.0),
                net_amount=float(payload.get("net_amount") or (float(payload.get("amount") or 0.0) - float(payload.get("fees") or 0.0))),
                status=payload.get("status") or "captured",
                settlement_batch_id=payload.get("settlement_batch_id"),
                bank_ref=payload.get("bank_ref"),
                utr=payload.get("utr"),
                payer_name=payload.get("payer_name"),
                payer_email=payload.get("payer_email"),
                raw_payload=str(payload),
            )
            session.add(txn)

        session.commit()
        session.refresh(txn)

        gross_amount = float(txn.amount)
        fees = float(txn.fees)
        tax_amount = float(payload.get("tax_amount") or 0.0)
        payment_journal = JournalEntry(
            id=str(uuid4()),
            entry_no=f"JRN-{txn.source}-{txn.source_txn_id}",
            entry_type="payment",
            source_type=txn.source,
            source_id=txn.id,
            narration=f"Captured payment {txn.source_txn_id} via {txn.payment_method}",
            currency=txn.currency,
            exchange_rate=1.0,
        )
        session.add(payment_journal)
        session.commit()
        session.refresh(payment_journal)

        postings = [
            {"account_code": "gateway_clearing_inr", "account_name": "Gateway Clearing - INR", "account_type": "clearing", "currency": txn.currency, "amount": gross_amount, "debit_credit": "debit"},
            {"account_code": "merchant_revenue_inr", "account_name": "Merchant Revenue - INR", "account_type": "revenue", "currency": txn.currency, "amount": gross_amount, "debit_credit": "credit"},
        ]
        if fees > 0:
            postings.extend([
                {"account_code": "gateway_fee_inr", "account_name": "Gateway Fee - INR", "account_type": "fees", "currency": txn.currency, "amount": fees, "debit_credit": "debit"},
                {"account_code": "gateway_clearing_inr", "account_name": "Gateway Clearing - INR", "account_type": "clearing", "currency": txn.currency, "amount": fees, "debit_credit": "credit"},
            ])
        if tax_amount > 0:
            postings.extend([
                {"account_code": "tax_payable_inr", "account_name": "Tax Payable - INR", "account_type": "tax", "currency": txn.currency, "amount": tax_amount, "debit_credit": "debit"},
                {"account_code": "merchant_revenue_inr", "account_name": "Merchant Revenue - INR", "account_type": "revenue", "currency": txn.currency, "amount": tax_amount, "debit_credit": "credit"},
            ])

        _create_postings_for_journal(session, payment_journal, postings)
        session.commit()
        return {"payment_transaction_id": txn.id, "source_txn_id": txn.source_txn_id, "status": txn.status, "amount": txn.amount}


def create_bank_statement_line(payload: Dict[str, Any]) -> Dict[str, Any]:
    statement_ref = payload.get("statement_ref") or payload.get("utr") or payload.get("reference")
    if not statement_ref:
        raise ValueError("statement_ref is required")

    with Session(engine) as session:
        existing = session.exec(select(BankStatementLine).where(BankStatementLine.statement_ref == statement_ref)).first()
        if existing:
            existing.amount = float(payload.get("amount") or existing.amount)
            existing.bank_name = payload.get("bank_name") or existing.bank_name
            existing.narration = payload.get("narration") or existing.narration
            bank_line = existing
        else:
            bank_line = BankStatementLine(
                id=str(uuid4()),
                bank_name=payload.get("bank_name", "default_bank"),
                statement_ref=statement_ref,
                utr=payload.get("utr"),
                amount=float(payload.get("amount") or 0.0),
                currency=payload.get("currency") or "INR",
                narration=payload.get("narration"),
                source_type=payload.get("source_type") or "deposit",
                status=payload.get("status") or "unmatched",
            )
            session.add(bank_line)

        session.commit()
        session.refresh(bank_line)

        # Create a bank settlement journal entry: Dr Bank Cash, Cr Gateway Clearing
        settlement_journal = JournalEntry(
            id=str(uuid4()),
            entry_no=f"JRN-BANK-{bank_line.statement_ref}",
            entry_type="bank",
            source_type="bank_statement",
            source_id=bank_line.id,
            narration=f"Bank settlement {bank_line.statement_ref}",
            currency=bank_line.currency,
            exchange_rate=1.0,
        )
        session.add(settlement_journal)
        session.commit()
        session.refresh(settlement_journal)
        postings = [
            {"account_code": "bank_cash_inr", "account_name": "Bank Cash - INR", "account_type": "bank", "currency": bank_line.currency, "amount": float(bank_line.amount), "debit_credit": "debit"},
            {"account_code": "gateway_clearing_inr", "account_name": "Gateway Clearing - INR", "account_type": "clearing", "currency": bank_line.currency, "amount": float(bank_line.amount), "debit_credit": "credit"},
        ]
        _create_postings_for_journal(session, settlement_journal, postings)
        session.commit()

        return {"bank_statement_line_id": bank_line.id, "statement_ref": bank_line.statement_ref, "amount": bank_line.amount}


def get_trial_balance() -> List[Dict[str, Any]]:
    with Session(engine) as session:
        accounts = session.exec(select(Account)).all()
        postings = session.exec(select(Posting)).all()
        balance_map = {acc.id: 0.0 for acc in accounts}
        for posting in postings:
            if posting.debit_credit == "debit":
                balance_map[posting.account_id] = balance_map.get(posting.account_id, 0.0) + float(posting.amount)
            else:
                balance_map[posting.account_id] = balance_map.get(posting.account_id, 0.0) - float(posting.amount)

        rows = []
        for acc in accounts:
            rows.append({
                "account_code": acc.account_code,
                "account_name": acc.account_name,
                "currency": acc.currency,
                "balance": round(balance_map.get(acc.id, 0.0), 2),
                "account_type": acc.account_type,
            })
        return rows


def reconcile_transaction(payload: Dict[str, Any]) -> Dict[str, Any]:
    payment_id = payload.get("payment_transaction_id") or payload.get("source_txn_id")
    bank_ref = payload.get("bank_statement_ref") or payload.get("statement_ref") or payload.get("bank_ref")

    with Session(engine) as session:
        txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.id == payment_id)).first() if payment_id else None
        if not txn and payment_id:
            txn = session.exec(select(PaymentTransaction).where(PaymentTransaction.source_txn_id == payment_id)).first()
        if not txn:
            raise ValueError("payment not found")

        bank_line = None
        if bank_ref:
            bank_line = session.exec(select(BankStatementLine).where(BankStatementLine.statement_ref == bank_ref)).first()

        if not bank_line:
            bank_line = session.exec(select(BankStatementLine).where(BankStatementLine.utr == txn.utr)).first() if txn.utr else None

        if bank_line is None:
            return {"matched": False, "reason": "no bank statement line matched"}

        amount_delta = abs(float(bank_line.amount) - float(txn.amount))
        time_delta = 0
        match_score = 1.0 if bank_line.utr == txn.utr or (bank_line.statement_ref and txn.bank_ref and bank_line.statement_ref == txn.bank_ref) else max(0.0, 1.0 - (amount_delta / max(float(txn.amount), 1.0)))

        rec = Reconciliation(
            id=str(uuid4()),
            source_type="payment",
            source_id=txn.id,
            payment_transaction_id=txn.id,
            bank_statement_line_id=bank_line.id,
            match_score=round(match_score, 4),
            rule_applied="amount_and_reference",
            status="matched" if match_score >= 0.8 else "open",
            notes=f"matched by amount/ref: delta={amount_delta}, time_delta={time_delta}",
        )
        session.add(rec)
        session.commit()
        return {
            "matched": match_score >= 0.8,
            "match_score": round(match_score, 4),
            "payment_transaction_id": txn.id,
            "bank_statement_line_id": bank_line.id,
            "status": rec.status,
        }
