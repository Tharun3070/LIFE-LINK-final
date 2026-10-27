"""Add dataset fields and blood bank / inventory tables.

Revision ID: 0007_dataset_fields_and_blood_banks
Revises: 0006_user_verification_and_license_fields
Create Date: 2026-10-25 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_dataset_fields_and_blood_banks'
down_revision: Union[str, None] = '0006_user_verification_and_license_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. New donor dataset columns
    with op.batch_alter_table('donors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True, server_default='Coimbatore'))
        batch_op.add_column(sa.Column('district', sa.String(length=100), nullable=True, server_default='Coimbatore'))
        batch_op.add_column(sa.Column('pincode', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('contact_number', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.String(length=50), nullable=True))

    # 2. New hospital / facility dataset columns
    with op.batch_alter_table('hospitals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=50), nullable=True, server_default='hospital'))
        batch_op.add_column(sa.Column('district', sa.String(length=100), nullable=True, server_default='Coimbatore'))
        batch_op.add_column(sa.Column('pincode', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('services', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('data_provenance', sa.String(length=50), nullable=True, server_default='production'))

    # 3. Create blood_banks table
    op.create_table(
        'blood_banks',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False, server_default='Coimbatore'),
        sa.Column('district', sa.String(length=100), nullable=True, server_default='Coimbatore'),
        sa.Column('pincode', sa.String(length=20), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('contact_number', sa.String(length=50), nullable=True),
        sa.Column('services', sa.String(length=255), nullable=True),
        sa.Column('hospital_id', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.String(length=50), nullable=True),
        sa.Column('updated_at', sa.String(length=50), nullable=True),
        sa.Column('data_provenance', sa.String(length=50), nullable=True, server_default='production'),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_blood_banks_id'), 'blood_banks', ['id'], unique=False)

    # 4. Create blood_inventories table
    op.create_table(
        'blood_inventories',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('blood_bank_id', sa.String(length=50), nullable=True),
        sa.Column('hospital_id', sa.String(length=50), nullable=True),
        sa.Column('blood_group', sa.String(length=10), nullable=False),
        sa.Column('component', sa.String(length=50), nullable=False, server_default='whole_blood'),
        sa.Column('units_available', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('units_reserved', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(['blood_bank_id'], ['blood_banks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_blood_inventories_id'), 'blood_inventories', ['id'], unique=False)
    op.create_index(op.f('ix_blood_inventories_blood_group'), 'blood_inventories', ['blood_group'], unique=False)


def downgrade() -> None:
    op.drop_table('blood_inventories')
    op.drop_table('blood_banks')
    with op.batch_alter_table('hospitals', schema=None) as batch_op:
        batch_op.drop_column('data_provenance')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('services')
        batch_op.drop_column('pincode')
        batch_op.drop_column('district')
        batch_op.drop_column('category')
    with op.batch_alter_table('donors', schema=None) as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('email')
        batch_op.drop_column('contact_number')
        batch_op.drop_column('pincode')
        batch_op.drop_column('district')
        batch_op.drop_column('city')
        batch_op.drop_column('name')
