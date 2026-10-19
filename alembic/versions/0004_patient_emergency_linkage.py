"""patient_emergency_linkage

Revision ID: 0004_patient_emergency_linkage
Revises: 0003_donor_synthetic_provenance
Create Date: 2026-10-18 19:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0004_patient_emergency_linkage'
down_revision: Union[str, None] = '0003_donor_synthetic_provenance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('emergencies') as batch_op:
        batch_op.add_column(sa.Column('patient_id', sa.String(length=50), nullable=True))
        batch_op.create_foreign_key(
            'fk_emergencies_patient_id_users',
            'users',
            ['patient_id'],
            ['id'],
            ondelete='SET NULL'
        )
        batch_op.create_index('ix_emergencies_patient_id', ['patient_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('emergencies') as batch_op:
        batch_op.drop_index('ix_emergencies_patient_id')
        batch_op.drop_constraint('fk_emergencies_patient_id_users', type_='foreignkey')
        batch_op.drop_column('patient_id')
