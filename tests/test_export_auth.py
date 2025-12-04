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
    resp = client.post("/bci/export", json={"format": "xdf"}, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 403
    assert "missing required scope" in resp.text


def test_raw_ws_requires_scope():
    client = TestClient(app)
    with client.websocket_connect("/bci/raw") as ws:
        data = ws.receive()
        assert data["type"] == "websocket.close"


def test_export_success_and_invalid_format(tmp_path, monkeypatch):
    client = TestClient(app)
    from src import server

    class AllowAuth:
        def authorize(self, token, required):
            return True

        def extract_token(self, *args, **kwargs):
            return "tok"

    server._auth = AllowAuth()  # type: ignore
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
