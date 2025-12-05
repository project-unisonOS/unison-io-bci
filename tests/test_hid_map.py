from fastapi.testclient import TestClient

from src.server import app
from src import server


class AllowAuth:
    def authorize(self, token, required=None):
        return True

    def extract_token(self, *args, **kwargs):
        return "tok"

    def authorize_with_claims(self, token, required_scope=None):
        return {"sub": "tester", "scopes": [required_scope] if required_scope else []}


def test_hid_map_rejects_invalid_key():
    client = TestClient(app)
    server.set_auth(AllowAuth())  # type: ignore
    resp = client.post("/bci/hid-map", json={"mappings": {"click": "NOT_A_KEY"}}, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 400


def test_hid_map_allows_valid_key():
    client = TestClient(app)
    server.set_auth(AllowAuth())  # type: ignore
    resp = client.post("/bci/hid-map", json={"mappings": {"click": "KEY_ENTER"}}, headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
