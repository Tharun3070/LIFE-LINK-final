"""Add audit hash chaining fields and rate limit records table.

Revision ID: 0010_audit_hash_chaining_and_rate_limits
Revises: 0009_emergency_location_coordinates
Create Date: 2026-10-26 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010_audit_hash_chaining_and_rate_limits'
down_revision: Union[str, None] = '0009_emergency_location_coordinates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    context = op.get_context()
    if getattr(context, "as_sql", False):
        with op.batch_alter_table('audit_logs', schema=None) as batch_op:
            batch_op.add_column(sa.Column('previous_hash', sa.String(64), nullable=True))
            batch_op.add_column(sa.Column('record_hash', sa.String(64), nullable=True))
            batch_op.create_index('ix_audit_logs_previous_hash', ['previous_hash'], unique=False)
            batch_op.create_index('ix_audit_logs_record_hash', ['record_hash'], unique=False)

        op.create_table(
            'rate_limit_records',
            sa.Column('key', sa.String(200), primary_key=True),
            sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('window_start', sa.Float(), nullable=False),
            sa.Column('expires_at', sa.Float(), nullable=False),
        )
        op.create_index('ix_rate_limit_records_expires_at', 'rate_limit_records', ['expires_at'], unique=False)
        return

    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Update audit_logs with hash-chaining columns and indexes inside batch_alter_table
    audit_cols = [c['name'] for c in inspector.get_columns('audit_logs')]
    existing_audit_indexes = [ix['name'] for ix in inspector.get_indexes('audit_logs')]

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        if 'previous_hash' not in audit_cols:
            batch_op.add_column(sa.Column('previous_hash', sa.String(64), nullable=True))
        if 'record_hash' not in audit_cols:
            batch_op.add_column(sa.Column('record_hash', sa.String(64), nullable=True))
        if 'ix_audit_logs_previous_hash' not in existing_audit_indexes:
            batch_op.create_index('ix_audit_logs_previous_hash', ['previous_hash'], unique=False)
        if 'ix_audit_logs_record_hash' not in existing_audit_indexes:
            batch_op.create_index('ix_audit_logs_record_hash', ['record_hash'], unique=False)

    # 2. Create rate_limit_records table if not present
    if 'rate_limit_records' not in inspector.get_table_names():
        op.create_table(
            'rate_limit_records',
            sa.Column('key', sa.String(200), primary_key=True),
            sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('window_start', sa.Float(), nullable=False),
            sa.Column('expires_at', sa.Float(), nullable=False),
        )
        op.create_index('ix_rate_limit_records_expires_at', 'rate_limit_records', ['expires_at'], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if 'rate_limit_records' in inspector.get_table_names():
        op.drop_table('rate_limit_records')

    existing_audit_indexes = [ix['name'] for ix in inspector.get_indexes('audit_logs')]
    existing_cols = [c['name'] for c in inspector.get_columns('audit_logs')]

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        if 'ix_audit_logs_record_hash' in existing_audit_indexes:
            batch_op.drop_index('ix_audit_logs_record_hash')
        if 'ix_audit_logs_previous_hash' in existing_audit_indexes:
            batch_op.drop_index('ix_audit_logs_previous_hash')
        if 'record_hash' in existing_cols:
            batch_op.drop_column('record_hash')
        if 'previous_hash' in existing_cols:
            batch_op.drop_column('previous_hash')
