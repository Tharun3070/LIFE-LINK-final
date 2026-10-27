"""Make hospital coordinates nullable and expand contact_number.

Revision ID: 0008_hospital_nullable_coordinates
Revises: 0007_dataset_fields_and_blood_banks
Create Date: 2026-10-25 20:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_hospital_nullable_coordinates'
down_revision: Union[str, None] = '0007_dataset_fields_and_blood_banks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('hospitals', schema=None) as batch_op:
        batch_op.alter_column('lat', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('lng', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('contact_number', existing_type=sa.String(length=50), type_=sa.String(length=255), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('hospitals', schema=None) as batch_op:
        batch_op.alter_column('contact_number', existing_type=sa.String(length=255), type_=sa.String(length=50), nullable=True)
        batch_op.alter_column('lng', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('lat', existing_type=sa.Float(), nullable=False)
