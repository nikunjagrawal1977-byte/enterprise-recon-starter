from alembic import op
import sqlalchemy as sa

revision = "20261019_ledger_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="reviewer"),
    )

    op.create_table(
        "account",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("account_code", sa.String(), nullable=False, unique=True),
        sa.Column("account_name", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False, server_default="merchant"),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("parent_account_id", sa.String(), sa.ForeignKey("account.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "journal_entry",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("entry_no", sa.String(), nullable=False, unique=True),
        sa.Column("entry_type", sa.String(), nullable=False, server_default="payment"),
        sa.Column("source_type", sa.String(), nullable=False, server_default="gateway"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("narration", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("exchange_rate", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "posting",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("journal_entry_id", sa.String(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("account_id", sa.String(), sa.ForeignKey("account.id"), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("debit_credit", sa.String(), nullable=False, server_default="debit"),
        sa.Column("posted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "payment_transaction",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="razorpay"),
        sa.Column("source_txn_id", sa.String(), nullable=False, unique=True),
        sa.Column("merchant_txn_id", sa.String(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=False, server_default="card"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("fees", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("net_amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(), nullable=False, server_default="captured"),
        sa.Column("payment_time", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("settlement_batch_id", sa.String(), nullable=True),
        sa.Column("bank_ref", sa.String(), nullable=True),
        sa.Column("utr", sa.String(), nullable=True),
        sa.Column("payer_name", sa.String(), nullable=True),
        sa.Column("payer_email", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.String(), nullable=True),
    )

    op.create_table(
        "settlement_batch",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("gateway", sa.String(), nullable=False, server_default="razorpay"),
        sa.Column("batch_no", sa.String(), nullable=False, unique=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("settlement_date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
    )

    op.create_table(
        "bank_statement_line",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("bank_name", sa.String(), nullable=False),
        sa.Column("statement_ref", sa.String(), nullable=False, unique=True),
        sa.Column("utr", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("entry_date", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("narration", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="deposit"),
        sa.Column("status", sa.String(), nullable=False, server_default="unmatched"),
    )

    op.create_table(
        "fx_rate",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("base_currency", sa.String(), nullable=False, server_default="INR"),
        sa.Column("quote_currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("rate", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("valid_from", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "reconciliation",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default="payment"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("journal_entry_id", sa.String(), sa.ForeignKey("journal_entry.id"), nullable=True),
        sa.Column("payment_transaction_id", sa.String(), sa.ForeignKey("payment_transaction.id"), nullable=True),
        sa.Column("bank_statement_line_id", sa.String(), sa.ForeignKey("bank_statement_line.id"), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rule_applied", sa.String(), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "exception",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("exception_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "candidate",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("exception_id", sa.String(), sa.ForeignKey("exception.id"), nullable=True),
        sa.Column("bank_settlement_id", sa.String(), nullable=True),
        sa.Column("gateway_txn_id", sa.String(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("payment_ts", sa.Integer(), nullable=True),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("bank_ref", sa.String(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
    )

    op.create_table(
        "audit",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("exception_id", sa.String(), sa.ForeignKey("exception.id"), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("audit")
    op.drop_table("candidate")
    op.drop_table("exception")
    op.drop_table("reconciliation")
    op.drop_table("fx_rate")
    op.drop_table("bank_statement_line")
    op.drop_table("settlement_batch")
    op.drop_table("payment_transaction")
    op.drop_table("posting")
    op.drop_table("journal_entry")
    op.drop_table("account")
    op.drop_table("user")
