import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.auth import AuthValidator


def test_authorize_missing_token():
    auth = AuthValidator()
    assert not auth.authorize("", required_scope := "bci.raw.read")


def test_extract_token():
    auth = AuthValidator()
    token = auth.extract_token("Bearer abc.def.ghi")
    assert token == "abc.def.ghi"
    assert auth.extract_token(None) is None


def test_scope_parsing_from_claims():
    auth = AuthValidator()
    claims = {"scope": "a bci.raw.read c"}
    scopes = auth.get_scopes_from_claims(claims)
    assert "bci.raw.read" in scopes
