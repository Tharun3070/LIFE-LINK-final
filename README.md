# LifeLink — Phase 1 Backend Foundation

**AI-Powered Emergency Healthcare Intelligence & Response Network**  
*"Connecting the right healthcare resource, at the right place, at the right time."*

---

## Overview

LifeLink is an emergency healthcare intelligence backend built with **FastAPI**, **Pydantic v2**, and **SQLAlchemy 2.x**. It provides a secure, typed, and extensible foundation for:
1. **Blood Donor Emergency Response**: Rapid SOS matching, dynamic radius expansion, and AI-ranked donor candidate retrieval.
2. **Organ Reachability & Viability Intelligence**: Cold ischemia viability countdowns, reachability scoring, and human-authorized clinical review workflows.
3. **Ambulance Live Tracking & Routing**: Multi-route comparison (Route A/B/C), traffic conditions, and trauma bay hospital preparation.
4. **Security & Governance**: JWT authentication, fine-grained Role-Based Access Control (RBAC), donor privacy consent management, and tamper-evident audit logging.

---

## Tech Stack

- **Language**: Python 3.12+ (Tested on Python 3.13)
- **Web Framework**: FastAPI
- **Data Validation**: Pydantic v2 & Pydantic Settings
- **ORM & Database**: SQLAlchemy 2.0 (SQLite for local rapid dev, PostgreSQL-ready architecture)
- **Security**: PyJWT, Argon2 / bcrypt password hashing
- **Testing**: Pytest & FastAPI TestClient (43 comprehensive unit & integration tests)
- **Real-Time**: WebSockets with ConnectionManager

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                     # App factory, CORS, exception handlers, lifecycle
│   ├── core/
│   │   ├── config.py               # Settings (.env, JWT secrets, CORS)
│   │   ├── security.py             # Password hashing, JWT token creation & decode
│   │   ├── permissions.py          # RBAC permissions and role mapping
│   │   ├── dependencies.py         # DB session, get_current_user, require_permission
│   │   └── logging.py              # Structured logging
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy DeclarativeBase
│   │   ├── session.py              # Engine and SessionLocal factory
│   │   └── init_db.py              # Database seeder with development dataset
│   ├── models/                     # SQLAlchemy 2.x ORM models
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   ├── services/                   # Business logic layer
│   ├── ai/                         # Abstract AI/ML interfaces (XGBoost, RAG, LLM)
│   ├── geo/                        # Abstract Geospatial & Google Maps interfaces
│   ├── realtime/                   # WebSocket connection manager & event schemas
│   └── api/
│       ├── router.py               # Aggregated v1 & compat routers
│       └── v1/                     # Endpoint controllers
├── tests/                          # Automated Pytest suite
├── docs/
│   ├── API_CONTRACT.md             # Complete REST & WebSocket API specification
│   └── ARCHITECTURE.md            # Phase 1 vs Future Roadmap
├── .env.example
├── requirements.txt
├── alembic.ini
└── README.md
```

---

## Quickstart & Installation

### 1. Create and Activate Virtual Environment
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy the template configuration:
```powershell
copy .env.example .env
```

### 4. Run Automated Tests
```powershell
pytest tests -v
```

### 5. Start the FastAPI Development Server
```powershell
uvicorn app.main:app --reload --port 8000
```

---

## API Documentation

Once the server is running, interactive documentation is available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Authentication & RBAC

LifeLink uses JWT authentication with standard 7 platform roles:

| Role | Default Demo Email | Permissions Scope |
|---|---|---|
| `doctor` | `doctor@lifelink.demo` | Command Center, Create Blood SOS, Review Organs, Track Ambulances, Audit Logs |
| `hospital_staff` | `staff@lifelink.demo` | Command Center, Blood SOS, Ambulance Ops, Hospital Inventory |
| `transplant_coordinator` | `transplant@lifelink.demo` | Organ Intelligence, Authorized Clinical Review, Audit Logs |
| `ambulance_operator` | `ambulance@lifelink.demo` | Ambulance Fleet, GPS Telemetry, Live Map |
| `donor` | `donor@lifelink.demo` | Donor Portal, Active SOS Acceptance, Privacy Consent Center |
| `patient` | `patient@lifelink.demo` | Patient Emergency Tracker, Next-of-Kin Telemetry |
| `admin` | `admin@lifelink.demo` | Platform Governance, User Management, Full System Access |

*Demo Accounts Password*: `{role}123` (e.g. `doctor123`, `admin123`).

---

## Frontend Integration

The backend is fully compatible with the existing LifeLink React frontend.
To connect the frontend to this FastAPI backend:
1. In `Life Link Project/.env`:
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_ENV=production
```
2. Start FastAPI (`uvicorn app.main:app --reload --port 8000`)
3. Start React frontend (`npm run dev`)
