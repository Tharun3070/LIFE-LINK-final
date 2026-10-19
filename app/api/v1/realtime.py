from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.realtime.manager import ws_manager
from app.core.logging import logger

router = APIRouter(tags=["Real-Time WebSockets"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Receive client messages / heartbeats
            data = await websocket.receive_text()
            logger.debug(f"Received WebSocket message: {data}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        ws_manager.disconnect(websocket)
