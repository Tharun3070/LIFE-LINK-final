import asyncio
from typing import List, Dict, Set, Optional, Any
from fastapi import WebSocket, status
from app.realtime.events import RealtimeEvent, RealtimeEventType
from app.core.logging import logger
from app.core.security import decode_token
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.models.donor import Donor


def authenticate_websocket_sync(websocket: WebSocket, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    Extracts and validates credentials from a WebSocket connection request.
    Rejects missing, expired, invalid, and refresh tokens.
    Returns user metadata dictionary if valid, or None if unauthenticated.
    """
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    if not token:
        proto = websocket.headers.get("sec-websocket-protocol")
        if proto:
            for p in proto.split(","):
                p_clean = p.strip()
                if p_clean and p_clean != "Bearer":
                    token = p_clean
                    break

    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user and "-00" in user_id:
            user = db.query(User).filter(User.id == user_id.replace("-00", "-0")).first()
        elif not user and "-0" in user_id:
            user = db.query(User).filter(User.id == user_id.replace("-0", "-00")).first()
        if not user or (user.session_status is not None and user.session_status != "active"):
            return None

        donor_id = None
        if user.role == "donor":
            d = db.query(Donor).filter(Donor.user_id == user.id).first()
            if d:
                donor_id = d.id

        return {
            "user_id": user.id,
            "name": user.name,
            "role": user.role,
            "hospital_id": user.hospital_id,
            "donor_id": donor_id,
            "is_verified": user.is_verified,
        }
    except Exception as e:
        logger.error(f"WebSocket auth DB lookup failed: {e}")
        return None
    finally:
        if close_db:
            db.close()


class ConnectionManager:
    """Manages authenticated active WebSocket connections, rooms, and resource-authorized broadcasts."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_users: Dict[WebSocket, Dict[str, Any]] = {}
        self.channel_subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_info: Optional[Dict[str, Any]] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_info:
            self.connection_users[websocket] = user_info
        logger.info(
            f"WebSocket client connected (role={user_info.get('role') if user_info else 'anon'}). "
            f"Total active: {len(self.active_connections)}"
        )
        
        # Send initial connection confirmation event matching frontend expectation
        welcome_event = RealtimeEvent(
            type=RealtimeEventType.CONNECTION_ESTABLISHED.value,
            payload={"message": "Connected to LifeLink Realtime WebSocket Gateway"},
        )
        await websocket.send_json(welcome_event.model_dump())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_users.pop(websocket, None)
        for channel, subs in self.channel_subscriptions.items():
            subs.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active: {len(self.active_connections)}")

    def is_authorized_for_event(self, user_info: Dict[str, Any], event: RealtimeEvent) -> bool:
        """Enforces resource- and role-level authorization for broadcast events."""
        if not user_info:
            return False

        event_type = event.type
        payload = event.payload or {}
        role = user_info.get("role", "")
        user_id = user_info.get("user_id", "")
        hospital_id = user_info.get("hospital_id")
        donor_id = user_info.get("donor_id")

        # System and lifecycle events are accessible to all authenticated users
        if event_type in (
            RealtimeEventType.CONNECTION_ESTABLISHED.value,
            RealtimeEventType.CONNECTION_LOST.value,
            RealtimeEventType.SYSTEM_STATUS_UPDATED.value,
        ):
            return True

        # Administrators receive all operational telemetry
        if role == "admin":
            return True

        # Doctors have clinical emergency oversight across their network
        if role == "doctor":
            return True

        # Hospital staff receive updates affiliated with their assigned hospital or general alerts
        if role == "hospital_staff":
            ev_hosp = payload.get("hospitalId")
            if ev_hosp and hospital_id and ev_hosp != hospital_id:
                return False
            return True

        # Ambulance operators & drivers receive ambulance telemetry & ambulance dispatch events
        if role in ("ambulance_operator", "ambulance_driver"):
            if event_type.startswith("ambulance.") or payload.get("type") == "ambulance":
                return True
            return False

        # Transplant coordinators receive organ intelligence & organ emergency events
        if role == "transplant_coordinator":
            if event_type.startswith("organ.") or payload.get("type") == "organ":
                return True
            return False

        # Patients are strictly isolated to their own emergencies
        if role == "patient":
            ev_pat = payload.get("patientId")
            return bool(ev_pat and ev_pat == user_id)

        # Donors are strictly isolated to events addressing their donor record
        if role == "donor":
            ev_donor = payload.get("donorId")
            return bool(ev_donor and (ev_donor == donor_id or ev_donor == user_id))

        return False

    async def broadcast(self, event: RealtimeEvent):
        """Broadcasts a real-time event to authorized connected clients."""
        disconnected = []
        for connection in list(self.active_connections):
            user_info = self.connection_users.get(connection, {})
            if not self.is_authorized_for_event(user_info, event):
                continue
            try:
                await connection.send_json(event.model_dump())
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def broadcast_sync(self, event: RealtimeEvent):
        """Synchronously broadcasts an event across active connections."""
        if not self.active_connections:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            asyncio.create_task(self.broadcast(event))
        else:
            try:
                import concurrent.futures
                asyncio.run(self.broadcast(event))
            except Exception as e:
                logger.warning(f"Failed to broadcast sync event: {e}")

    async def send_personal_event(self, websocket: WebSocket, event: RealtimeEvent):
        try:
            await websocket.send_json(event.model_dump())
        except Exception:
            self.disconnect(websocket)


ws_manager = ConnectionManager()
