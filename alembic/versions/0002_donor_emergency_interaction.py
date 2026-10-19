"""donor_emergency_interaction_v1

Revision ID: 0002_donor_emergency_interaction
Revises: 0001_initial_schema
Create Date: 2026-10-09 14:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_donor_emergency_interaction'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'donor_emergency_interactions',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('emergency_id', sa.String(length=50), nullable=False),
        sa.Column('donor_id', sa.String(length=50), nullable=False),
        sa.Column('selected_at', sa.String(length=50), nullable=False),
        # Snapshot features
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('eta_minutes', sa.Integer(), nullable=False),
        sa.Column('time_of_day_hours', sa.Float(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=False),
        sa.Column('emergency_priority', sa.String(length=30), nullable=False),
        sa.Column('compatibility_match_type', sa.String(length=30), nullable=False),
        sa.Column('donor_availability_at_selection', sa.String(length=30), nullable=False),
        sa.Column('donor_total_previous_donations', sa.Integer(), nullable=False),
        sa.Column('donor_days_since_last_donation', sa.Integer(), nullable=True),
        # Contact stage
        sa.Column('contact_status', sa.String(length=30), nullable=False),
        sa.Column('contact_channel', sa.String(length=30), nullable=True),
        sa.Column('contact_attempted_at', sa.String(length=50), nullable=True),
        sa.Column('contact_delivered_at', sa.String(length=50), nullable=True),
        # Response stage
        sa.Column('response_status', sa.String(length=30), nullable=False),
        sa.Column('responded_at', sa.String(length=50), nullable=True),
        sa.Column('response_latency_seconds', sa.Integer(), nullable=True),
        # Acceptance stage
        sa.Column('acceptance_status', sa.String(length=30), nullable=False),
        sa.Column('rejection_reason', sa.String(length=255), nullable=True),
        # Completion stage
        sa.Column('completion_status', sa.String(length=30), nullable=False),
        sa.Column('completed_at', sa.String(length=50), nullable=True),
        sa.Column('units_donated', sa.Integer(), nullable=True),
        # Provenance & Audit
        sa.Column('outcome_source', sa.String(length=50), nullable=False),
        sa.Column('data_provenance', sa.String(length=50), nullable=False),
        sa.Column('is_synthetic', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['donor_id'], ['donors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['emergency_id'], ['emergencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_donor_emergency_interactions_id'), 'donor_emergency_interactions', ['id'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_emergency_id'), 'donor_emergency_interactions', ['emergency_id'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_donor_id'), 'donor_emergency_interactions', ['donor_id'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_selected_at'), 'donor_emergency_interactions', ['selected_at'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_contact_status'), 'donor_emergency_interactions', ['contact_status'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_response_status'), 'donor_emergency_interactions', ['response_status'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_acceptance_status'), 'donor_emergency_interactions', ['acceptance_status'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_completion_status'), 'donor_emergency_interactions', ['completion_status'], unique=False)
    op.create_index(op.f('ix_donor_emergency_interactions_is_synthetic'), 'donor_emergency_interactions', ['is_synthetic'], unique=False)
    op.create_index('ix_dint_emergency_donor', 'donor_emergency_interactions', ['emergency_id', 'donor_id'], unique=False)
    op.create_index('ix_dint_synthetic_provenance', 'donor_emergency_interactions', ['is_synthetic', 'data_provenance'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_dint_synthetic_provenance', table_name='donor_emergency_interactions')
    op.drop_index('ix_dint_emergency_donor', table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_is_synthetic'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_completion_status'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_acceptance_status'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_response_status'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_contact_status'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_selected_at'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_donor_id'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_emergency_id'), table_name='donor_emergency_interactions')
    op.drop_index(op.f('ix_donor_emergency_interactions_id'), table_name='donor_emergency_interactions')
    op.drop_table('donor_emergency_interactions')
