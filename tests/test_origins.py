import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from server.main import app, origin_allowed

@pytest.mark.parametrize("origin", ["http://[", "http://[not-an-ip]", "http://testserver\uff0f.evil"])
def test_malformed_origin_is_denied(origin):
    assert not origin_allowed({"origin": origin, "host": "testserver"})

def test_malformed_http_origin_returns_403():
    with TestClient(app) as client:
        assert client.get("/api/health", headers={"origin": "http://["}).status_code == 403

@pytest.mark.parametrize("endpoint", ["/ws/dashboard", "/ws/monitor"])
def test_malformed_websocket_origin_is_closed(endpoint):
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(endpoint, headers={"origin": "http://["}):
                pass
        assert error.value.code == 1008
