import json
import logging
import time
from typing import Dict, List, Optional, Set

import httpx
from jose import jwt

logger = logging.getLogger("unison-io-bci.auth")


class AuthValidator:
    """JWT + optional consent introspection for scope enforcement."""

    def __init__(
        self,
        jwks_url: str | None = None,
        audience: str | None = None,
        issuer: str | None = None,
        consent_introspect_url: str | None = None,
        cache_ttl: int = 300,
    ) -> None:
        self.jwks_url = jwks_url
        self.audience = audience
        self.issuer = issuer
        self.consent_introspect_url = consent_introspect_url
        self.cache_ttl = cache_ttl
        self._jwks_cache: Dict[str, object] | None = None
        self._jwks_fetched_at: float = 0.0

    def _get_jwks(self) -> Dict[str, object] | None:
        if not self.jwks_url:
            return None
        now = time.time()
        if self._jwks_cache and (now - self._jwks_fetched_at) < self.cache_ttl:
            return self._jwks_cache
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(self.jwks_url)
                resp.raise_for_status()
                jwks = resp.json()
                self._jwks_cache = jwks
                self._jwks_fetched_at = now
                return jwks
        except Exception as exc:  # pragma: no cover
            logger.warning("jwks_fetch_failed %s", exc)
            return None

    def _decode_jwt(self, token: str) -> Optional[Dict[str, object]]:
        jwks = self._get_jwks()
        options = {"verify_aud": bool(self.audience)}
        try:
            if jwks:
                return jwt.decode(
                    token,
                    jwks,
                    algorithms=["RS256", "ES256", "HS256"],
                    audience=self.audience,
                    issuer=self.issuer,
                    options=options,
                )
            # Fallback to header-only decode (no verification)
            return jwt.get_unverified_claims(token)
        except Exception as exc:
            logger.warning("jwt_decode_failed %s", exc)
            return None

    def _introspect_consent(self, token: str) -> Optional[Dict[str, object]]:
        if not self.consent_introspect_url:
            return None
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.post(self.consent_introspect_url, json={"token": token})
                if resp.status_code != 200:
                    return None
                data = resp.json()
                return data if data.get("active") else None
        except Exception as exc:  # pragma: no cover
            logger.warning("consent_introspect_failed %s", exc)
            return None

    def extract_token(self, authorization_header: str | None, query_token: str | None = None) -> Optional[str]:
        if query_token:
            return query_token
        if not authorization_header:
            return None
        if authorization_header.lower().startswith("bearer "):
            return authorization_header.split(" ", 1)[1].strip()
        return None

    def get_scopes_from_claims(self, claims: Dict[str, object]) -> Set[str]:
        scopes: Set[str] = set()
        for key in ("scope", "scopes"):
            if key in claims:
                raw = claims[key]
                if isinstance(raw, str):
                    scopes.update({s.strip() for s in raw.split() if s.strip()})
                elif isinstance(raw, list):
                    scopes.update({str(s).strip() for s in raw})
        return scopes

    def authorize(self, token: str, required_scope: str | None = None) -> bool:
        if not token:
            return False
        claims = self._decode_jwt(token) or {}
        scopes = self.get_scopes_from_claims(claims)
        # Try consent introspection if scope not present
        if required_scope and required_scope not in scopes:
            consent_info = self._introspect_consent(token)
            if consent_info:
                consent_scopes = consent_info.get("scopes", [])
                scopes.update(consent_scopes if isinstance(consent_scopes, list) else [])
        if required_scope:
            return required_scope in scopes or "*" in scopes
        return True

    def authorize_with_claims(self, token: str, required_scope: str | None = None) -> Optional[Dict[str, object]]:
        if not token:
            return None
        claims = self._decode_jwt(token) or {}
        scopes = self.get_scopes_from_claims(claims)
        if required_scope and required_scope not in scopes:
            consent_info = self._introspect_consent(token)
            if consent_info:
                consent_scopes = consent_info.get("scopes", [])
                scopes.update(consent_scopes if isinstance(consent_scopes, list) else [])
        if required_scope and required_scope not in scopes and "*" not in scopes:
            return None
        claims["scopes"] = list(scopes)
        return claims
