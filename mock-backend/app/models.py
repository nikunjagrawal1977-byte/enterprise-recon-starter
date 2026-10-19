from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
import uuid

class User(SQLModel, table=True):
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str
    role: str = "reviewer"  # reviewer, admin, viewer


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
