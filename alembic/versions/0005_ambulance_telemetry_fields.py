"""Add telemetry source, last telemetry timestamp, and device ID to ambulances table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-18 20:17:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_ambulance_telemetry_fields'
down_revision: Union[str, None] = '0004_patient_emergency_linkage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('ambulances', schema=None) as batch_op:
        batch_op.add_column(sa.Column('telemetry_source', sa.String(length=30), nullable=True, server_default='operator_manual'))
        batch_op.add_column(sa.Column('last_telemetry_at', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('device_id', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('ambulances', schema=None) as batch_op:
        batch_op.drop_column('device_id')
        batch_op.drop_column('last_telemetry_at')
        batch_op.drop_column('telemetry_source')
