import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    OPEN_PATHS = {"/api/health", "/mcp/oauth/callback"}

    async def dispatch(self, request: Request, call_next):
        api_key = os.environ.get("MCP_LENS_API_KEY", "").strip()
        if not api_key:
            return await call_next(request)

        path = request.url.path
        if path in self.OPEN_PATHS or not path.startswith(("/api/", "/mcp/")):
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        if provided != api_key:
            logger.warning("Rejected request to %s: invalid or missing API key", path)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )
        return await call_next(request)
