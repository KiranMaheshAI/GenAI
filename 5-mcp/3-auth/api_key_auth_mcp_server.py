# API Key Auth — Client Sends Key to Server
# When you're running MCP over HTTP/SSE (not stdio), the client can pass an API key in headers.

# mcp_server_http.py — HTTP transport with API key validation
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
import os
import secrets

server = Server("secure-server")

# Valid API keys (in production, store hashed in DB)
VALID_API_KEYS = {
    "key_prod_abc123": {"user": "team-a", "role": "admin"},
    "key_prod_xyz789": {"user": "team-b", "role": "readonly"},
}

def validate_api_key(request: Request) -> dict | None:
    """Extract and validate API key from request headers."""
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        key = auth_header[7:]
        return VALID_API_KEYS.get(key)
    
    # Also check X-API-Key header
    api_key = request.headers.get("X-API-Key", "")
    return VALID_API_KEYS.get(api_key)

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [...]  # your tools

async def handle_sse(request: Request):
    # Validate before establishing SSE connection
    user_info = validate_api_key(request)
    if not user_info:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    # Attach user info to request state for use in tool calls
    request.state.user = user_info
    
    sse = SseServerTransport("/messages/")
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(*streams, server.create_initialization_options())

app = Starlette(routes=[
    Route("/sse", handle_sse),
    Mount("/messages/", app=SseServerTransport("/messages/").handle_post_message)
])

# Run with: uvicorn mcp_server_http:app --host 0.0.0.0 --port 8000