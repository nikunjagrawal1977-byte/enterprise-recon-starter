from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MatchCandidate(BaseModel):
    bank_settlement_id: Optional[str]
    gateway_txn_id: Optional[str]
    amount: Optional[float]
    payment_ts: Optional[int]
    payment_method: Optional[str]
    bank_ref: Optional[str]
    match_score: Optional[float]

    class Config:
        orm_mode = True


class AuditEntry(BaseModel):
    actor: str
    action: str
    at: datetime
    payload: Optional[dict] = None

    class Config:
        orm_mode = True


class ExceptionSummary(BaseModel):
    id: str
    exception_type: str
    reason: Optional[str]
    amount: Optional[float]
    created_at: datetime
    priority: Optional[str]
    status: str
    transaction_id: Optional[str]

    class Config:
        orm_mode = True


class ExceptionDetail(ExceptionSummary):
    transaction: Optional[dict] = None
    candidates: List[MatchCandidate] = []
    audit: List[AuditEntry] = []


class ManualMatchRequest(BaseModel):
    transaction_id: Optional[str]
    bank_settlement_id: Optional[str]
    action: str
    note: Optional[str] = None
    exception_id: Optional[str] = None
