# LifeLink API Contract & Specification

**Base URL**: `http://localhost:8000/api/v1` (Dual-mounted with `/api` for frontend backwards compatibility)  
**Authentication**: Standard OAuth2 / HTTP Bearer JWT Header (`Authorization: Bearer <token>`)

---

## 1. System & Health

### `GET /health`
- **Auth**: Public
- **Description**: Service health check
- **Response**: `200 OK`
```json
{
  "status": "ok",
  "service": "lifelink-backend",
  "version": "1.0.0",
  "environment": "development",
  "database": "connected"
}
```

### `GET /health/ready`
- **Auth**: Public
- **Response**: `200 OK` `{"status": "ready", "database": "connected"}`

### `GET /api/v1/system/status`
- **Auth**: Public
- **Response**: `200 OK`
```json
{
  "llm": "operational",
  "rag": "operational",
  "xgboost": "operational",
  "geospatial": "operational",
  "realtime": "operational",
  "database": "operational",
  "overallHealthy": true
}
```

---

## 2. Authentication & RBAC

### `POST /api/v1/auth/login`
- **Auth**: Public
- **Request**:
```json
{
  "identifier": "doctor@lifelink.demo",
  "password": "doctor123",
  "rememberMe": true
}
```
- **Response**: `200 OK`
```json
{
  "user": {
    "id": "usr-doc-001",
    "name": "Dr. Arjun Rao",
    "email": "doctor@lifelink.demo",
    "role": "doctor",
    "roleTitle": "Senior Emergency Physician",
    "hospitalId": "city-hospital-001",
    "hospitalName": "City General Hospital",
    "organization": "City Healthcare Network",
    "permissions": ["view_command_center", "create_blood_emergency", "manage_blood_emergency", "view_organ_intelligence", "manage_ambulance", "view_live_map", "view_analytics", "view_audit_logs"],
    "avatar": null,
    "isVerified": true,
    "lastLogin": "2026-08-29T18:30:00Z",
    "sessionStatus": "active"
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expiresAt": 1788000000
}
```

### `GET /api/v1/auth/me`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` (User Profile Object)

### `POST /api/v1/auth/logout`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` `{"message": "Logged out successfully"}`

### `POST /api/v1/auth/refresh`
- **Auth**: Public
- **Request**: `{"refresh_token": "..."}`
- **Response**: `200 OK` `{"access_token": "...", "token_type": "bearer", "expires_in": 7200, "refresh_token": "..."}`

---

## 3. Emergencies & Command Center

### `GET /api/v1/emergencies`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` Array of `Emergency`:
```json
[
  {
    "id": "BL-102",
    "type": "blood",
    "priority": "critical",
    "status": "resource_search",
    "hospitalId": "city-hospital-001",
    "hospitalName": "City General Hospital",
    "createdAt": "2026-08-29T18:20:00Z",
    "updatedAt": "2026-08-29T18:22:00Z",
    "description": "Emergency O- blood required for trauma surgery",
    "eta": 11,
    "assignedResourceIds": ["D-101", "D-104"],
    "bloodGroup": "O-",
    "unitsRequired": 3
  }
]
```

### `POST /api/v1/emergencies`
- **Auth**: Role: `doctor`, `hospital_staff`, `admin`
- **Request**:
```json
{
  "type": "blood",
  "priority": "critical",
  "hospitalId": "city-hospital-001",
  "description": "Emergency O- blood required for trauma surgery",
  "bloodGroup": "O-",
  "unitsRequired": 3
}
```
- **Response**: `200 OK` (Created `Emergency` object)

### `GET /api/v1/dashboard/kpis`
- **Auth**: Public / Bearer
- **Response**: `200 OK`
```json
{
  "activeEmergencies": 3,
  "bloodRequests": 2,
  "organAlerts": 1,
  "ambulancesActive": 4,
  "avgResponseTimeSeconds": 258,
  "donorAcceptanceRate": 72
}
```

### `GET /api/v1/activity?emergencyId={id}`
- **Auth**: Public / Bearer
- **Response**: `200 OK` Array of `EmergencyEvent`

---

## 4. Blood Module & Donor Intelligence

### `POST /api/v1/blood/requests` (and `/api/v1/blood/emergency`)
- **Auth**: Role: `doctor`, `hospital_staff`, `admin`
- **Request**:
```json
{
  "bloodGroup": "O-",
  "unitsRequired": 3,
  "priority": "critical",
  "hospitalId": "city-hospital-001",
  "notes": "Emergency surgery"
}
```
- **Response**: `200 OK` (`Emergency` object)

### `GET /api/v1/blood/donors/ranked?emergencyId={id}`
- **Auth**: Role: `doctor`, `hospital_staff`, `admin`
- **Response**: `200 OK`
```json
{
  "donors": [
    {
      "id": "D-101",
      "bloodGroup": "O-",
      "distanceKm": 3.2,
      "etaMinutes": 8,
      "eligibility": "eligible",
      "responseProbability": 91,
      "reliabilityScore": 94,
      "reachabilityScore": 92,
      "aiRank": 1,
      "status": "contacted",
      "locationConsentGranted": false,
      "historicalAcceptanceRate": 94,
      "coordinates": { "lat": 12.975, "lng": 77.590 }
    }
  ],
  "searchConfig": {
    "initialRadiusKm": 2.0,
    "currentRadiusKm": 5.0,
    "maxRadiusKm": 15.0,
    "expansionCount": 1,
    "expansionReason": "Insufficient eligible responses within initial 2km radius."
  },
  "aiRecommendation": "Donor #D-101 is preferred because of high historical response reliability (94%) and optimal arrival time."
}
```

### `POST /api/v1/blood/donors/{donor_id}/contact`
- **Auth**: Role: `doctor`, `hospital_staff`, `admin`
- **Request**: `{"emergencyId": "BL-102"}`
- **Response**: `200 OK` `{"status": "contacted", "donorId": "D-101", "contactedAt": "..."}`

### `POST /api/v1/blood/donors/{donor_id}/response`
- **Auth**: Public / Donor
- **Request**: `{"status": "accepted", "shareLocation": true}`
- **Response**: `200 OK`

---

## 5. Organ Intelligence & Clinical Governance

### `GET /api/v1/organs` (and `/api/v1/organs/available`)
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` Array of `OrganAvailability`
```json
[
  {
    "id": "ORG-K-001",
    "organType": "kidney",
    "sourceHospitalId": "apollo-001",
    "sourceHospitalName": "Apollo Transplant Center",
    "distanceKm": 14.0,
    "etaMinutes": 18,
    "viabilityRemainingSeconds": 16320,
    "viabilityTotalSeconds": 129600,
    "viabilityLevel": "normal",
    "reachabilityScore": 92,
    "aiRecommendation": "proceed",
    "aiRationale": "Organ is within reachability threshold. ETA 18 min is well within viability window.",
    "status": "clinical_review",
    "clinicalReviewStatus": "pending",
    "availableAt": "2026-08-29T18:00:00Z",
    "updatedAt": "2026-08-29T18:25:00Z"
  }
]
```

### `POST /api/v1/organs/{organ_id}/clinical-review`
- **Auth**: Role: `doctor`, `transplant_coordinator`, `admin`
- **Request**: `{"decision": "approved", "notes": "Recipient HLA verified"}`
- **Response**: `200 OK` (Updated Organ model)

---

## 6. Ambulance Routing & Fleet Telemetry

### `GET /api/v1/ambulances`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` Array of `Ambulance`

### `GET /api/v1/ambulances/{id}/routes`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK` Array of `RouteOption` (Route A, Route B, Route C)

### `POST /api/v1/ambulances/{id}/location`
- **Auth**: Role: `ambulance_operator`, `admin`
- **Request**: `{"lat": 12.965, "lng": 77.592, "speedKmh": 62.0, "heading": 45.0}`
- **Response**: `200 OK`

---

## 7. Audit & Consent

### `GET /api/v1/audit`
- **Auth**: Permission: `view_audit_logs`
- **Query Params**: `?module=blood&status=success&search=Dr.`
- **Response**: `200 OK` Array of `AuditLog`

### `GET /api/v1/consent` & `PATCH /api/v1/consent`
- **Auth**: `Bearer <token>`
- **Response**: `200 OK`
```json
{
  "id": "cns-001",
  "userId": "usr-dnr-005",
  "liveLocation": true,
  "emergencyCommunication": true,
  "donationRequests": true,
  "healthDataSharing": true,
  "updatedAt": "2026-08-29T18:30:00Z"
}
```

---

## 8. Real-Time WebSockets

### `WS /api/v1/ws` and `WS /ws`
- **Payload Format**:
```json
{
  "type": "emergency.updated",
  "payload": {
    "emergencyId": "BL-102",
    "status": "coordinating"
  },
  "timestamp": "2026-08-29T18:30:00Z"
}
```
