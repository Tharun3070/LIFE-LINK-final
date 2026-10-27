"""Add user verification status and professional license fields.

Revision ID: 0006_user_verification_and_license_fields
Revises: 0005_ambulance_telemetry_fields
Create Date: 2026-10-25 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_user_verification_and_license_fields'
down_revision: Union[str, None] = '0005_ambulance_telemetry_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('verification_status', sa.String(length=30), nullable=False, server_default='approved'))
        batch_op.add_column(sa.Column('phone', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('medical_license_number', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('driving_license_number', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('vehicle_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('verification_notes', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('verified_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('verified_by', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_users_verification_status', ['verification_status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_verification_status')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('verified_by')
        batch_op.drop_column('verified_at')
        batch_op.drop_column('verification_notes')
        batch_op.drop_column('vehicle_id')
        batch_op.drop_column('driving_license_number')
        batch_op.drop_column('medical_license_number')
        batch_op.drop_column('phone')
        batch_op.drop_column('verification_status')
