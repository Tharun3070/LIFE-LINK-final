# LifeLink Architectural Specification

## Phase 1 Foundation vs. Future Phases

```
┌─────────────────────────────────────────────────────────────┐
│                       React Frontend                        │
│          (Command Center, Blood, Organs, Ambulance)          │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON & WebSockets
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend Foundation                 │
│   ├── Pydantic v2 Validation Schemas                        │
│   ├── JWT Auth & RBAC Security Boundary (Argon2 / bcrypt)    │
│   ├── Business Services (Emergencies, Blood, Organs, AMB)   │
│   ├── Tamper-Evident Audit Logging & Consent Enforcement   │
│   └── WebSocket Connection Manager                          │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼ (IMPLEMENTED NOW)             ▼ (PHASE 2-7 PLANNED)
┌───────────────────────────────┐ ┌───────────────────────────┐
│     SQLAlchemy Persistence    │ │   AI / External Engines   │
│  ├── Users, Roles, Sessions   │ │  ├── LLM Intent Parsing   │
│  ├── Hospitals & Inventory    │ │  ├── Authorized RAG Vector│
│  ├── Emergencies & Events     │ │  ├── XGBoost Ranking      │
│  ├── Donors & Consents        │ │  ├── PostGIS Spatial      │
│  ├── Organs & Reviews         │ │  ├── Twilio Alerts        │
│  └── Ambulances & Routes      │ │  └── Google Maps Routes   │
└───────────────────────────────┘ └───────────────────────────┘
```

---

## Implemented Now (Phase 1)
- **FastAPI Core**: Uvicorn server, lifespan database initialization, custom error serialization.
- **Data Modeling & Validation**: Pydantic v2 models and SQLAlchemy 2.x declarative models mirroring frontend TypeScript definitions.
- **Authentication & RBAC**: JWT access/refresh token lifecycle, bcrypt password hashing, fine-grained permission dependencies (`require_role`, `require_permission`).
- **Emergency Management**: Command Center KPIs, live emergency state machine (`created` -> `resource_search` -> `coordinating` -> `resolved`), immutable activity logs.
- **Blood Response**: Emergency request intake, ranked candidate retrieval, donor contact tracking, response recording.
- **Organ Intelligence**: Viability countdown tracking, reachability scores, human-in-the-loop clinical review authorization.
- **Ambulance Intelligence**: Fleet tracking, route comparison options (Route A, B, C), telemetry location updates.
- **Audit & Privacy**: Append-only audit logger, donor consent toggling.
- **Real-Time WebSockets**: `/ws` and `/api/v1/ws` connection manager with event envelopes.

---

## Planned for Future Phases
- **Phase 2**: PostgreSQL Migration + PostGIS Spatial Indexing + PGVector Vector Database.
- **Phase 3**: End-to-end Blood Emergency automated event dispatch pipeline.
- **Phase 4**: XGBoost inference model training and production serving.
- **Phase 5**: Authorized RAG vector indexing with medical compatibility embeddings and LLM intent reasoning.
- **Phase 6**: Live Twilio SMS and Voice IVR automated dispatch.
- **Phase 7**: Google Maps Routes API with live traffic matrix.
