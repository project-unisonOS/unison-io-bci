from fastapi.testclient import TestClient

from src.server import app


def test_decoders_endpoint_lists_defaults():
    client = TestClient(app)
    resp = client.get("/bci/decoders")
    assert resp.status_code == 200
    data = resp.json()
    assert "decoders" in data
    assert any(d.get("name") == "window" for d in data["decoders"])
