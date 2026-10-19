"""initial_schema_v2

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-29 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Hospitals Table
    op.create_table(
        'hospitals',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('lat', sa.Float(), nullable=False),
        sa.Column('lng', sa.Float(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('blood_bank_available', sa.Boolean(), nullable=False),
        sa.Column('organ_transplant_center', sa.Boolean(), nullable=False),
        sa.Column('emergency_bays', sa.Integer(), nullable=False),
        sa.Column('contact_number', sa.String(length=50), nullable=True),
        sa.Column('is_current_hospital', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_hospitals_id'), 'hospitals', ['id'], unique=False)

    # 2. Users Table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('role_title', sa.String(length=100), nullable=True),
        sa.Column('hospital_id', sa.String(length=50), nullable=True),
        sa.Column('hospital_name', sa.String(length=150), nullable=True),
        sa.Column('organization', sa.String(length=150), nullable=True),
        sa.Column('avatar', sa.String(length=255), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('last_login', sa.String(length=50), nullable=True),
        sa.Column('session_status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_hospital_id'), 'users', ['hospital_id'], unique=False)

    # 3. Consents Table
    op.create_table(
        'consents',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('live_location', sa.Boolean(), nullable=False),
        sa.Column('emergency_communication', sa.Boolean(), nullable=False),
        sa.Column('donation_requests', sa.Boolean(), nullable=False),
        sa.Column('health_data_sharing', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_consents_id'), 'consents', ['id'], unique=False)
    op.create_index(op.f('ix_consents_user_id'), 'consents', ['user_id'], unique=True)

    # 4. Donors Table
    op.create_table(
        'donors',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=True),
        sa.Column('blood_group', sa.String(length=10), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('eta_minutes', sa.Integer(), nullable=False),
        sa.Column('eligibility', sa.String(length=30), nullable=False),
        sa.Column('eligibility_reason', sa.String(length=255), nullable=True),
        sa.Column('response_probability', sa.Integer(), nullable=False),
        sa.Column('reliability_score', sa.Integer(), nullable=False),
        sa.Column('reachability_score', sa.Integer(), nullable=False),
        sa.Column('ai_rank', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('location_consent_granted', sa.Boolean(), nullable=False),
        sa.Column('last_donation_days', sa.Integer(), nullable=True),
        sa.Column('historical_acceptance_rate', sa.Integer(), nullable=False),
        sa.Column('contacted_at', sa.String(length=50), nullable=True),
        sa.Column('responded_at', sa.String(length=50), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_donors_id'), 'donors', ['id'], unique=False)
    op.create_index(op.f('ix_donors_user_id'), 'donors', ['user_id'], unique=False)
    op.create_index(op.f('ix_donors_blood_group'), 'donors', ['blood_group'], unique=False)
    op.create_index(op.f('ix_donors_status'), 'donors', ['status'], unique=False)

    # 5. Emergencies Table
    op.create_table(
        'emergencies',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('priority', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('hospital_id', sa.String(length=50), nullable=False),
        sa.Column('hospital_name', sa.String(length=150), nullable=False),
        sa.Column('created_at', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('eta', sa.Integer(), nullable=True),
        sa.Column('assigned_resource_ids', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.String(length=50), nullable=True),
        sa.Column('blood_group', sa.String(length=10), nullable=True),
        sa.Column('units_required', sa.Integer(), nullable=True),
        sa.Column('organ_type', sa.String(length=50), nullable=True),
        sa.Column('origin', sa.String(length=150), nullable=True),
        sa.Column('destination', sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emergencies_id'), 'emergencies', ['id'], unique=False)
    op.create_index(op.f('ix_emergencies_type'), 'emergencies', ['type'], unique=False)
    op.create_index(op.f('ix_emergencies_priority'), 'emergencies', ['priority'], unique=False)
    op.create_index(op.f('ix_emergencies_status'), 'emergencies', ['status'], unique=False)
    op.create_index(op.f('ix_emergencies_hospital_id'), 'emergencies', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_emergencies_created_at'), 'emergencies', ['created_at'], unique=False)

    # 6. Emergency Events Table
    op.create_table(
        'emergency_events',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('emergency_id', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.String(length=50), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('resource', sa.String(length=150), nullable=True),
        sa.Column('authorization', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['emergency_id'], ['emergencies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_emergency_events_id'), 'emergency_events', ['id'], unique=False)
    op.create_index(op.f('ix_emergency_events_emergency_id'), 'emergency_events', ['emergency_id'], unique=False)
    op.create_index(op.f('ix_emergency_events_timestamp'), 'emergency_events', ['timestamp'], unique=False)

    # 7. Organs Table
    op.create_table(
        'organs',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('organ_type', sa.String(length=50), nullable=False),
        sa.Column('source_hospital_id', sa.String(length=50), nullable=False),
        sa.Column('source_hospital_name', sa.String(length=150), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('eta_minutes', sa.Integer(), nullable=False),
        sa.Column('viability_remaining_seconds', sa.Integer(), nullable=False),
        sa.Column('viability_total_seconds', sa.Integer(), nullable=False),
        sa.Column('viability_level', sa.String(length=20), nullable=False),
        sa.Column('reachability_score', sa.Integer(), nullable=False),
        sa.Column('ai_recommendation', sa.String(length=30), nullable=False),
        sa.Column('ai_rationale', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('clinical_review_status', sa.String(length=30), nullable=False),
        sa.Column('authorized_coordinator_id', sa.String(length=50), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('available_at', sa.String(length=50), nullable=False),
        sa.Column('updated_at', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['source_hospital_id'], ['hospitals.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['authorized_coordinator_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organs_id'), 'organs', ['id'], unique=False)
    op.create_index(op.f('ix_organs_organ_type'), 'organs', ['organ_type'], unique=False)
    op.create_index(op.f('ix_organs_source_hospital_id'), 'organs', ['source_hospital_id'], unique=False)
    op.create_index(op.f('ix_organs_status'), 'organs', ['status'], unique=False)

    # 8. Ambulances Table
    op.create_table(
        'ambulances',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('unit_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('driver_name', sa.String(length=100), nullable=True),
        sa.Column('origin', sa.String(length=150), nullable=True),
        sa.Column('destination', sa.String(length=150), nullable=True),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lng', sa.Float(), nullable=True),
        sa.Column('heading', sa.Float(), nullable=True),
        sa.Column('speed_kmh', sa.Float(), nullable=True),
        sa.Column('eta_minutes', sa.Integer(), nullable=True),
        sa.Column('routes_json', sa.Text(), nullable=True),
        sa.Column('selected_route_id', sa.String(length=50), nullable=True),
        sa.Column('hospital_id', sa.String(length=50), nullable=False),
        sa.Column('emergency_id', sa.String(length=50), nullable=True),
        sa.Column('dispatched_at', sa.String(length=50), nullable=True),
        sa.Column('arrived_at', sa.String(length=50), nullable=True),
        sa.Column('updated_at', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['hospital_id'], ['hospitals.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['emergency_id'], ['emergencies.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('unit_number')
    )
    op.create_index(op.f('ix_ambulances_id'), 'ambulances', ['id'], unique=False)
    op.create_index(op.f('ix_ambulances_unit_number'), 'ambulances', ['unit_number'], unique=True)
    op.create_index(op.f('ix_ambulances_status'), 'ambulances', ['status'], unique=False)
    op.create_index(op.f('ix_ambulances_hospital_id'), 'ambulances', ['hospital_id'], unique=False)
    op.create_index(op.f('ix_ambulances_emergency_id'), 'ambulances', ['emergency_id'], unique=False)

    # 9. Audit Logs Table (Tamper-Evident Immutable History)
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.String(length=50), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=False),
        sa.Column('actor_type', sa.String(length=30), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('resource', sa.String(length=150), nullable=False),
        sa.Column('resource_id', sa.String(length=50), nullable=True),
        sa.Column('authorization', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('session_id', sa.String(length=100), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_audit_logs_resource_id'), 'audit_logs', ['resource_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_module'), 'audit_logs', ['module'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('ambulances')
    op.drop_table('organs')
    op.drop_table('emergency_events')
    op.drop_table('emergencies')
    op.drop_table('donors')
    op.drop_table('consents')
    op.drop_table('users')
    op.drop_table('hospitals')
