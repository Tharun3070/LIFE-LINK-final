# LifeLink Database Architecture & Production Manual

## 1. Overview & Dual Architecture

LifeLink employs a dual-tier database architecture using **SQLAlchemy 2.x ORM** and **Alembic**:
* **Development & Automated Testing**: Lightweight, embedded **SQLite** database (`backend/lifelink.db` / `:memory:`).
* **Production Deployment**: **PostgreSQL 15+** with connection pooling (`QueuePool`), relational integrity constraints, and PostGIS preparation (`psycopg3` driver).

---

## 2. Configuration & Connection Strings

| Environment | Recommended `DATABASE_URL` | Driver |
|---|---|---|
| **Local Development** | `sqlite:///./lifelink.db` | Built-in `sqlite3` |
| **Testing / CI** | `sqlite:///:memory:` | `sqlite3` + `StaticPool` |
| **Production PostgreSQL** | `postgresql+psycopg://<user>:<password>@<host>:5432/<dbname>` | `psycopg` (psycopg 3 binary) |

### Automatic URL Normalization
In `app/core/config.py`, standard URLs such as `postgres://...` or `postgresql://...` are automatically mapped to `postgresql+psycopg://` to use the high-performance C-optimized psycopg3 driver.

---

## 3. Relational Schema & Integrity Constraints

```
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │    hospitals    │◄──────┤      users      │◄──────┤    consents     │
 └────────┬────────┘       └────────┬────────┘       └─────────────────┘
          │ (RESTRICT)              │ (SET NULL)
          ├─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │   emergencies   │◄──────┤     donors      │       │     organs      │
 └────────┬────────┘       └─────────────────┘       └─────────────────┘
          │ (CASCADE)
          ▼
 ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
 │emergency_events │       │   ambulances    │       │   audit_logs    │
 └─────────────────┘       └─────────────────┘       └─────────────────┘
```

### Foreign Key Constraints & Cascade Rules
1. `users.hospital_id` -> `hospitals.id` (`ON DELETE SET NULL`)
2. `donors.user_id` -> `users.id` (`ON DELETE SET NULL`)
3. `consents.user_id` -> `users.id` (`ON DELETE CASCADE`, unique 1-to-1)
4. `emergencies.hospital_id` -> `hospitals.id` (`ON DELETE RESTRICT`)
5. `emergency_events.emergency_id` -> `emergencies.id` (`ON DELETE CASCADE`)
6. `organs.source_hospital_id` -> `hospitals.id` (`ON DELETE RESTRICT`)
7. `organs.authorized_coordinator_id` -> `users.id` (`ON DELETE SET NULL`)
8. `ambulances.hospital_id` -> `hospitals.id` (`ON DELETE RESTRICT`)
9. `ambulances.emergency_id` -> `emergencies.id` (`ON DELETE SET NULL`)
10. `audit_logs`: Intentionally preserves loose actor/resource references to ensure **immutable audit history** cannot be broken by entity deletions.

### Unique Constraints
* `users.email` (Unique)
* `consents.user_id` (Unique)
* `ambulances.unit_number` (Unique, e.g. `AMB-042`)

---

## 4. Alembic Migration Workflow

Alembic configuration is situated in [`backend/alembic.ini`](file:///d:/Life%20link%20🖤🖤/backend/alembic.ini) and [`backend/alembic/`](file:///d:/Life%20link%20🖤🖤/backend/alembic).

### Common Migration Commands

* **Apply all pending migrations to the latest version**:
  ```powershell
  alembic upgrade head
  ```
* **Generate a new migration based on ORM model changes**:
  ```powershell
  alembic revision --autogenerate -m "describe_changes"
  ```
* **Rollback the last migration**:
  ```powershell
  alembic downgrade -1
  ```
* **Inspect current database revision**:
  ```powershell
  alembic current
  ```

---

## 5. PostGIS Preparation (Geospatial Foundation)

LifeLink is designed for zero-disruption PostGIS spatial indexing in future phases:
1. **Dual Coordinate Representation**: Models preserve explicit `lat` / `lng` float fields for API response compatibility.
2. **PostgreSQL Extension**: When `POSTGIS_ENABLED=true`, spatial queries will utilize PostGIS `geography(Point, 4326)` for radius containment (`ST_DWithin`) and KNN distance sorting (`<->`).

---

## 6. Development vs. Production Lifecycle

| Action | Development (`APP_ENV=development`) | Production (`APP_ENV=production`) |
|---|---|---|
| **DDL Creation** | Auto `create_all()` if SQLite | Relies strictly on `alembic upgrade head` |
| **Demo Seeding** | Auto-seeds demo data if empty | Disabled (`AUTO_SEED_DATA=false`) |
| **Connection Pooling** | Single-threaded SQLite / NullPool | `QueuePool` (Size: 10, Max Overflow: 20, Recycle: 300s) |
