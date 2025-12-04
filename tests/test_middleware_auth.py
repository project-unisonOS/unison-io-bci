from fastapi.testclient import TestClient
from src import server
from src.server import app


class AllowAuth:
    def authorize(self, token, required=None):
        return True

    def extract_token(self, *args, **kwargs):
        return "tok"

    def authorize_with_claims(self, token, required_scope=None):
        return {"sub": "test", "scopes": [required_scope or "dummy"]}


class DenyAuth:
    def authorize(self, token, required=None):
        return False

    def extract_token(self, *args, **kwargs):
        return "tok"

    def authorize_with_claims(self, token, required_scope=None):
        return None


def test_middleware_allows_and_sets_claims(monkeypatch):
    server._auth = AllowAuth()  # type: ignore
    client = TestClient(app)
    r = client.get("/health", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200


def test_middleware_blocks_invalid_token(monkeypatch):
    server._auth = DenyAuth()  # type: ignore
    client = TestClient(app)
    r = client.get("/health", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 403
