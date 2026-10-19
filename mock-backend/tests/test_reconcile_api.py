import os
import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine, SQLModel

# Ensure we use an in-memory DB for tests
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import main
from app import db as db_module
from app import seed


@pytest.fixture(scope='module')
def test_app():
    # create in-memory engine and patch db
    engine = create_engine('sqlite:///:memory:', connect_args={"check_same_thread": False})
    db_module.engine = engine
    SQLModel.metadata.create_all(engine)
    seed.create_initial_data()
    client = TestClient(main.app)
    yield client


def test_reconcile_end_to_end(test_app):
    client = test_app
    # login
    resp = client.post('/api/v1/auth/login', data={'username': 'admin', 'password': 'adminpass'})
    assert resp.status_code == 200
    token = resp.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    # create payment
    payload = {
        "source": "razorpay",
        "source_txn_id": "pay_api_1",
        "merchant_txn_id": "ORD-API-1",
        "payment_method": "upi",
        "amount": 1500.0,
        "currency": "INR",
        "fees": 15.0,
        "tax_amount": 0.0,
        "status": "captured",
    }
    r = client.post('/api/v1/transactions', json=payload, headers=headers)
    assert r.status_code == 200
    payment_id = r.json()['result']['payment_transaction_id']

    # create bank line
    bank_payload = {
        "bank_name": "Test Bank",
        "statement_ref": "UTR-API-1",
        "utr": "UTR-API-1",
        "amount": 1500.0,
        "currency": "INR",
        "narration": "settlement for pay_api_1",
    }
    r2 = client.post('/api/v1/bank_lines', json=bank_payload, headers=headers)
    assert r2.status_code == 200
    bank_line_id = r2.json()['result']['bank_statement_line_id']

    # get candidates
    r3 = client.get(f'/api/v1/reconciliation/candidates/{payment_id}', headers=headers)
    assert r3.status_code == 200
    data = r3.json()
    assert 'candidates' in data

    # force match
    r4 = client.post('/api/v1/reconciliation/force-match', json={'payment_transaction_id': payment_id, 'bank_statement_line_id': bank_line_id}, headers=headers)
    assert r4.status_code == 200
    assert r4.json()['result']['matched'] is True

    # check trial balance endpoint
    r5 = client.get('/api/v1/ledger/trial_balance', headers=headers)
    assert r5.status_code == 200
    tb = r5.json()['trial_balance']
    assert isinstance(tb, list)

    # list unmatched (should not include this payment)
    r6 = client.get('/api/v1/reconciliation/unmatched', headers=headers)
    assert r6.status_code == 200
    # ensure payment not in unmatched list
    unmatched = r6.json()['unmatched']
    assert all(item['id'] != payment_id for item in unmatched)
