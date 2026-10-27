"""Add location_lat and location_lng coordinates to emergencies table.

Revision ID: 0009_emergency_location_coordinates
Revises: 0008_hospital_nullable_coordinates
Create Date: 2026-10-25 22:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_emergency_location_coordinates'
down_revision: Union[str, None] = '0008_hospital_nullable_coordinates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    context = op.get_context()
    if getattr(context, "as_sql", False):
        with op.batch_alter_table('emergencies', schema=None) as batch_op:
            batch_op.add_column(sa.Column('location_lat', sa.Float(), nullable=True))
            batch_op.add_column(sa.Column('location_lng', sa.Float(), nullable=True))
        return

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('emergencies')]
    with op.batch_alter_table('emergencies', schema=None) as batch_op:
        if 'location_lat' not in existing_cols:
            batch_op.add_column(sa.Column('location_lat', sa.Float(), nullable=True))
        if 'location_lng' not in existing_cols:
            batch_op.add_column(sa.Column('location_lng', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('emergencies', schema=None) as batch_op:
        batch_op.drop_column('location_lng')
        batch_op.drop_column('location_lat')
