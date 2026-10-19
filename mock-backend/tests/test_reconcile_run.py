import os
from sqlmodel import create_engine, SQLModel, Session
import importlib

# Set up test database and patch engine references
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import app.db as db
from app import models

# create an in-memory engine and replace
engine = create_engine('sqlite:///:memory:', connect_args={"check_same_thread": False})
db.engine = engine

# ensure modules that imported engine at top-level use the test engine
import app.ledger as ledger
importlib.reload(ledger)

# create tables
SQLModel.metadata.create_all(engine)

# seed
import app.seed as seed
seed.create_initial_data()

# create a payment txn and bank line, then attempt reconcile
session = Session(engine)

# create payment
payload = {
    "source": "razorpay",
    "source_txn_id": "pay_test_1",
    "merchant_txn_id": "ORD-1",
    "payment_method": "upi",
    "amount": 1000.0,
    "currency": "INR",
    "fees": 10.0,
    "tax_amount": 0.0,
    "status": "captured",
}
res = ledger.create_payment_transaction(payload)

# ingest bank line
bank_payload = {
    "bank_name": "Test Bank",
    "statement_ref": "UTR-TEST-1",
    "utr": "UTR-TEST-1",
    "amount": 1000.0,
    "currency": "INR",
    "narration": "settlement for pay_test_1",
}
res2 = ledger.create_bank_statement_line(bank_payload)

# reload reconcile and run auto
import app.reconcile as reconcile
importlib.reload(reconcile)
stats = reconcile.run_auto_reconcile(limit=50)
print('reconcile stats:', stats)
