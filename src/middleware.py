from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

from .auth import AuthValidator


class ScopeMiddleware(BaseHTTPMiddleware):
    """Attach auth claims to request.state.claims when a bearer token is present."""

    def __init__(self, app, auth: AuthValidator):
        super().__init__(app)
        self.auth = auth

    async def dispatch(self, request: Request, call_next: Callable):
        token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        if token:
            claims = self.auth.authorize_with_claims(token)
            if claims is None:
                raise HTTPException(status_code=403, detail="invalid or unauthorized token")
            request.state.claims = claims
        return await call_next(request)
