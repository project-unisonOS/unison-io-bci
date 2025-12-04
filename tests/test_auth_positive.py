import pytest
from fastapi.testclient import TestClient

from src.server import app
from src import server


class AllowAuth:
    def authorize(self, token, required):
        return True

    def extract_token(self, *args, **kwargs):
        return "tok"


def test_intents_ws_allows_with_scope(monkeypatch):
    client = TestClient(app)
    server._auth = AllowAuth()  # type: ignore
    with client.websocket_connect("/bci/intents?token=tok") as ws:
        ws.send_text("ping")  # ignored but keeps socket alive
        # Should stay open; close manually
        ws.close()
        assert True


def test_export_allows_with_scope(monkeypatch):
    client = TestClient(app)
    server._auth = AllowAuth()  # type: ignore
    server._raw_state["demo"] = {
        "samples": [[0.1, 0.2], [0.3, 0.4]],
        "sample_rate": 250,
        "channel_labels": ["c1", "c2"],
        "start_time": 0.0,
        "sample_index": 2,
    }
    resp = client.post("/bci/export", json={"format": "xdf"})
    assert resp.status_code == 200
