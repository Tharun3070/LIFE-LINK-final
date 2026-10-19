# LifeLink — Managed PostgreSQL Production Deployment Guide

## 1. Overview
This runbook guides the operations and DevOps teams in deploying LifeLink against an enterprise-managed PostgreSQL 16+ instance (AWS RDS Aurora PostgreSQL, Google Cloud SQL, or Azure Database for PostgreSQL).

---

## 2. Environment Configuration Template

Create or update your production `.env` file using the following template (**placeholders only, do not commit secrets**):

```bash
# ------------------------------------------------------------------------------
# Core Environment
# ------------------------------------------------------------------------------
APP_ENV=production
DEBUG=False
VERSION=2.0.0
HOST=0.0.0.0
PORT=8000

# ------------------------------------------------------------------------------
# Security & JWT Credentials
# ------------------------------------------------------------------------------
JWT_SECRET_KEY=REPLACE_WITH_CRYPTOGRAPHICALLY_SECURE_64_CHAR_HEX_SECRET
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ------------------------------------------------------------------------------
# Managed PostgreSQL Connection
# Recommended driver: psycopg 3 (postgresql+psycopg://...)
# ------------------------------------------------------------------------------
DATABASE_URL=postgresql+psycopg://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:<DB_PORT>/<DB_NAME>?sslmode=require

# Connection Pooling
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
AUTO_SEED_DATA=False
POSTGIS_ENABLED=True

# ------------------------------------------------------------------------------
# Production Telephony & Notification Credentials (Twilio)
# ------------------------------------------------------------------------------
NOTIFICATION_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TWILIO_AUTH_TOKEN=REPLACE_WITH_TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
TWILIO_LIVE_ENABLED=False  # Switch to True only after operator validation
MOCK_NOTIFICATIONS_ONLY=False
NOTIFICATION_RATE_LIMIT_PER_RECIPIENT_PER_HOUR=5
NOTIFICATION_SPEND_CEILING_USD=100.0

# ------------------------------------------------------------------------------
# Frontend & CORS
# ------------------------------------------------------------------------------
CORS_ORIGINS=["https://app.lifelink.health", "https://admin.lifelink.health"]
```

---

## 3. Database Initialization & Extensions

Connect to the PostgreSQL instance with administrator privileges to create the database and required extensions:

```sql
-- 1. Create database
CREATE DATABASE lifelink_production
    WITH OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    CONNECTION LIMIT = -1;

\c lifelink_production

-- 2. Enable recommended performance and GIS extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gist";
-- If spatial indexing is utilized:
CREATE EXTENSION IF NOT EXISTS "postgis";

-- 3. Dedicated least-privilege application user
CREATE USER lifelink_app WITH ENCRYPTED PASSWORD 'SECURE_APPLICATION_USER_PASSWORD';
GRANT CONNECT ON DATABASE lifelink_production TO lifelink_app;
GRANT USAGE, CREATE ON SCHEMA public TO lifelink_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lifelink_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO lifelink_app;
```

---

## 4. Running Migrations

Execute the Alembic migration chain from the backend directory:

```bash
# Verify current migration head
alembic current

# Run all migrations up to head (0001 -> 0005)
alembic upgrade head

# Confirm migration head matches expected revision
alembic heads
# Expected output: 0005_ambulance_telemetry_fields (head)
```

### Rollback Procedure
If a migration needs to be rolled back to a previous state:

```bash
# Roll back by one revision:
alembic downgrade -1

# Roll back to specific revision:
alembic downgrade 0004_patient_emergency_linkage
```

---

## 5. Data Migration & Validation Runbook

When transferring baseline tables (hospitals, initial roles) from staging to production:

1. **Pre-Migration Backup**:
   ```bash
   pg_dump -h <STAGING_HOST> -U <STAGING_USER> -d <STAGING_DB> \
     --data-only \
     --table=hospitals \
     --file=staging_hospitals.sql
   ```

2. **Data Ingestion**:
   ```bash
   psql -h <PROD_HOST> -U lifelink_app -d lifelink_production -f staging_hospitals.sql
   ```

3. **Integrity & Row-Count Verification**:
   ```sql
   SELECT 'hospitals' AS table_name, count(*) AS row_count FROM hospitals
   UNION ALL
   SELECT 'users', count(*) FROM users
   UNION ALL
   SELECT 'emergencies', count(*) FROM emergencies;
   ```

4. **Foreign Key and Constraint Verification**:
   ```sql
   -- Check for orphan emergency patient references
   SELECT e.id, e.patient_id FROM emergencies e
   LEFT JOIN users u ON e.patient_id = u.id
   WHERE e.patient_id IS NOT NULL AND u.id IS NULL;
   -- Must return 0 rows.
   ```

---

## 6. Backup, Recovery, and Point-In-Time Restore (PITR)

### Automated Daily Snapshots
Ensure managed database service has automated snapshots enabled with a minimum 30-day retention window.

### Manual Full Backup
```bash
pg_dump -h <PROD_HOST> -U lifelink_admin -d lifelink_production \
  -F c -b -v -f "/secure_backups/lifelink_prod_$(date +%Y%m%d_%H%M%S).dump"
```

### Disaster Recovery Restore
```bash
# Restore to a clean recovery database:
createdb -h <RECOVERY_HOST> -U lifelink_admin lifelink_recovery
pg_restore -h <RECOVERY_HOST> -U lifelink_admin -d lifelink_recovery -v "/secure_backups/lifelink_prod_20261018.dump"
```

---

## 7. Health & Readiness Verification

Once deployed, monitor the application's native health endpoints:

- **Liveness Probe**: `GET https://<api-host>/health`
  - Expected: HTTP 200 `{"status": "ok", "service": "lifelink-backend", ...}`
- **Readiness Probe**: `GET https://<api-host>/health/ready`
  - Executes `SELECT 1` on the PostgreSQL connection pool.
  - Expected: HTTP 200 `{"status": "ready", "database": "connected", ...}`
- **Notification Provider Status**: `GET https://<api-host>/api/v1/notifications/provider-status`
  - Expected: HTTP 200 with configured provider parameters.

---

## 8. Connection Pool Sizing Formula

Recommended connection pool configuration for containerized deployment:

$$\text{Pool Size per Container} = \frac{\text{PostgreSQL max\_connections} \times 0.8}{\text{Number of API Replicas}}$$

- Default container pool: `DB_POOL_SIZE=20`, `DB_MAX_OVERFLOW=10`.
- Timeout: `DB_POOL_TIMEOUT=30` seconds.
- Recycle: `DB_POOL_RECYCLE=1800` seconds (30 minutes) to prevent stale connections across load balancers.

---

## 9. Dedicated Integration Testing & Safety Guard Harness

To verify complete end-to-end integration against an isolated, disposable PostgreSQL database before deployment:

### Safety Guard Requirements
1. The target database **MUST** use the PostgreSQL dialect (`postgresql` or `postgresql+psycopg`).
2. The database name **MUST** contain an explicit test identifier: `test`, `disposable`, `sandbox`, or `ci` (e.g. `lifelink_disposable_test`).
3. Execution is strictly refused if the target matches `lifelink`, `lifelink_prod`, `lifelink_production`, `postgres`, `defaultdb`, or any SQLite file.
4. Twilio live sending is automatically forced to `TWILIO_LIVE_ENABLED=False` and `MOCK_NOTIFICATIONS_ONLY=True`.

### Provisioning an Isolated Test Database
```bash
# Docker disposable test container:
docker run --name lifelink-pg-test \
  -e POSTGRES_USER=lifelink_test_user \
  -e POSTGRES_PASSWORD=disposable_test_pass_2026 \
  -e POSTGRES_DB=lifelink_disposable_test \
  -p 5432:5432 -d postgres:16-alpine
```

### Running the Integration Suite
Set the environment variable and run the automated verification script:

**PowerShell (Windows):**
```powershell
$env:LIFELINK_POSTGRES_TEST_URL = "postgresql+psycopg://lifelink_test_user:disposable_test_pass_2026@localhost:5432/lifelink_disposable_test"
python scripts/verify_postgresql_integration.py
```

**Bash (Linux / macOS):**
```bash
export LIFELINK_POSTGRES_TEST_URL="postgresql+psycopg://lifelink_test_user:disposable_test_pass_2026@localhost:5432/lifelink_disposable_test"
python scripts/verify_postgresql_integration.py
```

Or execute directly through pytest:
```bash
python -m pytest tests/test_postgresql_live_integration.py -v
```

