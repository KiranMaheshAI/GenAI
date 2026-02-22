# jwt_auth_server.py
# JWT-Based Auth — Stateless & Scalable
# Good for microservices where you don't want shared state.

import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

server = Server("jwt-server")
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = "HS256"

# ── Token Generation (your login endpoint) ────────────────────

async def login(request: Request):
    """Issue a JWT token after credential verification."""
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    
    # In production: verify against DB with hashed passwords
    if username == "admin" and password == "secret":
        payload = {
            "sub": username,
            "role": "admin",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=8)
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return JSONResponse({"token": token})
    
    return JSONResponse({"error": "Invalid credentials"}, status_code=401)

# ── Token Validation ──────────────────────────────────────────

def verify_jwt(request: Request) -> dict | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    
    token = auth[7:]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # token expired
    except jwt.InvalidTokenError:
        return None  # bad token

# ── Role-Based Access Control ─────────────────────────────────

TOOL_PERMISSIONS = {
    "read_data":   ["admin", "readonly", "editor"],
    "write_data":  ["admin", "editor"],
    "delete_data": ["admin"],
}

def check_permission(role: str, tool_name: str) -> bool:
    allowed_roles = TOOL_PERMISSIONS.get(tool_name, [])
    return role in allowed_roles

# ── MCP Tools with RBAC ───────────────────────────────────────

from mcp import types

# Store request context (simplified — in production use contextvars)
current_user: dict = {}

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    role = current_user.get("role", "readonly")
    
    # Dynamically return tools based on user's role
    all_tools = [
        types.Tool(name="read_data", description="Read data", inputSchema={"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}),
        types.Tool(name="write_data", description="Write data", inputSchema={"type": "object", "properties": {"key": {"type": "string"}, "value": {"type": "string"}}, "required": ["key", "value"]}),
        types.Tool(name="delete_data", description="Delete data", inputSchema={"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}),
    ]
    
    # Only show tools the user can access
    return [t for t in all_tools if check_permission(role, t.name)]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    role = current_user.get("role", "")
    
    if not check_permission(role, name):
        return [types.TextContent(type="text", text=f"Access denied: your role '{role}' cannot use '{name}'")]
    
    # Fake data store for demo
    data_store = {}
    
    if name == "read_data":
        value = data_store.get(arguments["key"], "not found")
        return [types.TextContent(type="text", text=str(value))]
    
    elif name == "write_data":
        data_store[arguments["key"]] = arguments["value"]
        return [types.TextContent(type="text", text="Written successfully")]
    
    elif name == "delete_data":
        data_store.pop(arguments["key"], None)
        return [types.TextContent(type="text", text="Deleted")]

# ── SSE with JWT Auth ─────────────────────────────────────────

async def handle_sse(request: Request):
    global current_user
    
    user = verify_jwt(request)
    if not user:
        return JSONResponse({"error": "Unauthorized — provide a valid JWT"}, status_code=401)
    
    current_user = user  # attach user context
    
    sse = SseServerTransport("/messages/")
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(*streams, server.create_initialization_options())

app = Starlette(routes=[
    Route("/login", login, methods=["POST"]),
    Route("/sse", handle_sse),
    Mount("/messages/", app=SseServerTransport("/messages/").handle_post_message)
])