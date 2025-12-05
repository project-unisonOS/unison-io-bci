import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.server import app, REQUIRED_SCOPE_EXPORT


def test_export_requires_scope(monkeypatch):
    client = TestClient(app)
    # Disable JWKS/consent by monkeypatching _require_scope_request to use an always-false auth validator
    from src import server

    class DummyAuth:
        def authorize(self, token, required=None):
            return False if required else True

        def extract_token(self, *args, **kwargs):
            return "tok"

        def authorize_with_claims(self, token, required_scope=None):
            return {"scopes": []}

    server.set_auth(DummyAuth())  # type: ignore
    resp = client.post("/bci/export", json={"format": "xdf"}, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 403
    assert "missing required scope" in resp.text or "unauthorized" in resp.text


def test_raw_ws_requires_scope():
    client = TestClient(app)
    from src import server

    class NoScopeAuth:
        def authorize(self, token, required=None):
            return False

        def extract_token(self, *args, **kwargs):
            return None

        def authorize_with_claims(self, token, required_scope=None):
            return None

    server.set_auth(NoScopeAuth())  # type: ignore
    try:
        with client.websocket_connect("/bci/raw") as ws:
            msg = ws.receive()
            assert msg["type"] == "websocket.close"
    except WebSocketDisconnect as exc:
        assert exc.code == 4403


def test_export_success_and_invalid_format(tmp_path, monkeypatch):
    client = TestClient(app)
    from src import server

    class AllowAuth:
        def authorize(self, token, required):
            return True

        def extract_token(self, *args, **kwargs):
            return "tok"

        def authorize_with_claims(self, token, required_scope=None):
            return {"scopes": [required_scope] if required_scope else []}

    server.set_auth(AllowAuth())  # type: ignore
    # Seed raw state with dummy samples
    server._raw_state["demo"] = {
        "samples": [[1.0, 2.0], [3.0, 4.0]],
        "sample_rate": 250,
        "channel_labels": ["c1", "c2"],
        "start_time": 0.0,
        "sample_index": 2,
    }
    # Invalid format
    resp_bad = client.post("/bci/export", json={"format": "txt"})
    assert resp_bad.status_code == 400
    # Valid XDF
    resp = client.post("/bci/export", json={"format": "xdf"}, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    assert "file" in resp.json()
    # Valid EDF
    resp_edf = client.post("/bci/export", json={"format": "edf"})
    assert resp_edf.status_code == 200
