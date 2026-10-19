"""donor_synthetic_provenance

Revision ID: 0003_donor_synthetic_provenance
Revises: 0002_donor_emergency_interaction
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_donor_synthetic_provenance'
down_revision: Union[str, None] = '0002_donor_emergency_interaction'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('donors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_synthetic', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('data_provenance', sa.String(length=50), nullable=False, server_default='production'))
        batch_op.add_column(sa.Column('simulated_coordinates', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_index('ix_donors_is_synthetic', ['is_synthetic'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('donors', schema=None) as batch_op:
        batch_op.drop_index('ix_donors_is_synthetic')
        batch_op.drop_column('simulated_coordinates')
        batch_op.drop_column('data_provenance')
        batch_op.drop_column('is_synthetic')
