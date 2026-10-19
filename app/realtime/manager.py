import asyncio
from typing import List, Dict, Set
from fastapi import WebSocket
from app.realtime.events import RealtimeEvent, RealtimeEventType
from app.core.logging import logger


class ConnectionManager:
    """Manages active WebSocket connections, rooms, and broadcasts."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.channel_subscriptions: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total active: {len(self.active_connections)}")
        
        # Send initial connection confirmation event matching frontend expectation
        welcome_event = RealtimeEvent(
            type=RealtimeEventType.CONNECTION_ESTABLISHED.value,
            payload={"message": "Connected to LifeLink Realtime WebSocket Gateway"},
        )
        await websocket.send_json(welcome_event.model_dump())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        for channel, subs in self.channel_subscriptions.items():
            subs.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, event: RealtimeEvent):
        """Broadcasts a real-time event to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
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
                # Run the coroutine to completion
                asyncio.run(self.broadcast(event))
            except Exception as e:
                logger.warning(f"Failed to broadcast sync event: {e}")

    async def send_personal_event(self, websocket: WebSocket, event: RealtimeEvent):
        try:
            await websocket.send_json(event.model_dump())
        except Exception:
            self.disconnect(websocket)


ws_manager = ConnectionManager()
