import pytest
from fastapi.testclient import TestClient

from src.server import app, REQUIRED_SCOPE_EXPORT


def test_export_requires_scope(monkeypatch):
    client = TestClient(app)
    # Disable JWKS/consent by monkeypatching _require_scope_request to use an always-false auth validator
    from src import server

    class DummyAuth:
        def authorize(self, token, required):
            return False

        def extract_token(self, *args, **kwargs):
            return "tok"

    server._auth = DummyAuth()  # type: ignore
    resp = client.post("/bci/export", json={"format": "xdf"})
    assert resp.status_code == 403
    assert "missing required scope" in resp.text


def test_raw_ws_requires_scope():
    client = TestClient(app)
    with client.websocket_connect("/bci/raw") as ws:
        data = ws.receive()
        assert data["type"] == "websocket.close"
