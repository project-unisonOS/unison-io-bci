from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

from .auth import AuthValidator


class ScopeMiddleware(BaseHTTPMiddleware):
    """Attach auth claims to request.state.claims when a bearer token is present."""

    def __init__(self, app, auth: AuthValidator):
        super().__init__(app)
        self.auth = auth

    async def dispatch(self, request: Request, call_next: Callable):
        auth = getattr(request.app.state, "auth", self.auth)
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if token:
            claims_fn = getattr(auth, "authorize_with_claims", None)
            claims = claims_fn(token) if claims_fn else None
            if claims is None:
                authorize_fn = getattr(auth, "authorize", None)
                ok = False
                if authorize_fn:
                    try:
                        ok = bool(authorize_fn(token))
                    except TypeError:
                        try:
                            ok = bool(authorize_fn(token, None))  # type: ignore[misc]
                        except Exception:
                            ok = False
                if ok:
                    claims = {"token": token, "scopes": []}
            if claims is None:
                return JSONResponse(status_code=403, content={"detail": "invalid or unauthorized token"})
            request.state.claims = claims  # type: ignore[assignment]
        return await call_next(request)
