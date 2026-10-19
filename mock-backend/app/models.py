from __future__ import annotations
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
import uuid


class User(SQLModel, table=True):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = "reviewer"


class Account(SQLModel, table=True):
    __tablename__ = "account"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    account_code: str = Field(index=True, unique=True)
    account_name: str
    account_type: str = "merchant"
    currency: str = "INR"
    parent_account_id: Optional[str] = Field(default=None, foreign_key="account.id")
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    parent: Optional["Account"] = Relationship(sa_relationship_kwargs={"remote_side": "Account.id"})
    postings: List["Posting"] = Relationship(back_populates="account")


class JournalEntry(SQLModel, table=True):
    __tablename__ = "journal_entry"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    entry_no: str = Field(index=True, unique=True)
    entry_type: str = "payment"
    source_type: str = "gateway"
    source_id: Optional[str] = None
    narration: str
    currency: str = "INR"
    exchange_rate: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    postings: List["Posting"] = Relationship(back_populates="journal_entry")


class Posting(SQLModel, table=True):
    __tablename__ = "posting"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    journal_entry_id: Optional[str] = Field(default=None, foreign_key="journal_entry.id")
    account_id: Optional[str] = Field(default=None, foreign_key="account.id")
    amount: float = 0.0
    currency: str = "INR"
    debit_credit: str = "debit"
    posted_at: datetime = Field(default_factory=datetime.utcnow)

    journal_entry: Optional[JournalEntry] = Relationship(back_populates="postings")
    account: Optional[Account] = Relationship(back_populates="postings")


class PaymentTransaction(SQLModel, table=True):
    __tablename__ = "payment_transaction"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source: str = "razorpay"
    source_txn_id: str = Field(index=True, unique=True)
    merchant_txn_id: Optional[str]
    payment_method: str = "card"
    amount: float = 0.0
    currency: str = "INR"
    fees: float = 0.0
    net_amount: float = 0.0
    status: str = "captured"
    payment_time: datetime = Field(default_factory=datetime.utcnow)
    settlement_batch_id: Optional[str] = None
    bank_ref: Optional[str] = None
    utr: Optional[str] = None
    payer_name: Optional[str] = None
    payer_email: Optional[str] = None
    raw_payload: Optional[str] = None


class SettlementBatch(SQLModel, table=True):
    __tablename__ = "settlement_batch"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    gateway: str = "razorpay"
    batch_no: str = Field(index=True, unique=True)
    amount: float = 0.0
    currency: str = "INR"
    settlement_date: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"


class BankStatementLine(SQLModel, table=True):
    __tablename__ = "bank_statement_line"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    bank_name: str
    statement_ref: str = Field(index=True, unique=True)
    utr: Optional[str]
    amount: float = 0.0
    currency: str = "INR"
    entry_date: datetime = Field(default_factory=datetime.utcnow)
    narration: Optional[str]
    source_type: str = "deposit"
    status: str = "unmatched"


class FxRate(SQLModel, table=True):
    __tablename__ = "fx_rate"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    base_currency: str = "INR"
    quote_currency: str = "USD"
    rate: float = 1.0
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_to: Optional[datetime] = None


class Reconciliation(SQLModel, table=True):
    __tablename__ = "reconciliation"
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source_type: str = "payment"
    source_id: Optional[str] = None
    journal_entry_id: Optional[str] = Field(default=None, foreign_key="journal_entry.id")
    payment_transaction_id: Optional[str] = Field(default=None, foreign_key="payment_transaction.id")
    bank_statement_line_id: Optional[str] = Field(default=None, foreign_key="bank_statement_line.id")
    match_score: float = 0.0
    rule_applied: str = "manual"
    status: str = "open"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Exception(SQLModel, table=True):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    exception_type: str
    reason: Optional[str]
    amount: Optional[float]
    priority: str = "medium"
    status: str = "open"
    transaction_id: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    candidates: List["Candidate"] = Relationship(back_populates="exception")
    audits: List["Audit"] = Relationship(back_populates="exception")


class Candidate(SQLModel, table=True):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    exception_id: Optional[str] = Field(default=None, foreign_key="exception.id")
    bank_settlement_id: Optional[str]
    gateway_txn_id: Optional[str]
    amount: Optional[float]
    payment_ts: Optional[int]
    payment_method: Optional[str]
    bank_ref: Optional[str]
    match_score: Optional[float]

    exception: Optional[Exception] = Relationship(back_populates="candidates")


class Audit(SQLModel, table=True):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    exception_id: Optional[str] = Field(default=None, foreign_key="exception.id")
    actor: str
    action: str
    note: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    exception: Optional[Exception] = Relationship(back_populates="audits")
