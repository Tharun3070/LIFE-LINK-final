import pytest
from starlette.websockets import WebSocketDisconnect
from app.core.security import create_refresh_token


def test_anonymous_websocket_connection_rejected(client):
    """Anonymous WebSocket connections must be rejected with policy violation (1008)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 1008


def test_anonymous_websocket_v1_connection_rejected(client):
    """Anonymous API v1 WebSocket connections must be rejected with policy violation (1008)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws"):
            pass
    assert exc_info.value.code == 1008


def test_refresh_token_websocket_connection_rejected(client):
    """Refresh tokens cannot be used to connect to the WebSocket gateway."""
    refresh_token = create_refresh_token(subject="usr-doc-001", role="doctor")
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws?token={refresh_token}"):
            pass
    assert exc_info.value.code == 1008


def test_websocket_connection(client, doctor_token):
    """Authenticated client with access token receives connection.established event."""
    with client.websocket_connect(f"/ws?token={doctor_token}") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection.established"
        assert "message" in data["payload"]


def test_websocket_v1_connection(client, doctor_token):
    """Authenticated client on API v1 route receives connection.established event."""
    with client.websocket_connect(f"/api/v1/ws?token={doctor_token}") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection.established"
