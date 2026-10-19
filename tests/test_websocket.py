def test_websocket_connection(client):
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection.established"
        assert "message" in data["payload"]


def test_websocket_v1_connection(client):
    with client.websocket_connect("/api/v1/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection.established"
