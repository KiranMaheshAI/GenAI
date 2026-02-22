# oauth_mcp_server.py
import os
import json
import time
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route, Mount
from mcp import types

server = Server("oauth-server")

# OAuth config (e.g., GitHub OAuth App)
OAUTH_CLIENT_ID = os.environ["OAUTH_CLIENT_ID"]
OAUTH_CLIENT_SECRET = os.environ["OAUTH_CLIENT_SECRET"]
OAUTH_REDIRECT_URI = "http://localhost:8000/callback"

# In-memory token store (use Redis/DB in production)
token_store: dict[str, dict] = {}
pending_states: dict[str, str] = {}  # state -> session_id

# ── OAuth Routes ────────────────────────────────────────────

async def oauth_authorize(request: Request):
    """Start OAuth flow — redirect user to GitHub."""
    import secrets
    state = secrets.token_urlsafe(32)
    session_id = request.query_params.get("session_id", "default")
    pending_states[state] = session_id
    
    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={OAUTH_CLIENT_ID}"
        f"&redirect_uri={OAUTH_REDIRECT_URI}"
        f"&scope=repo,user"
        f"&state={state}"
    )
    return RedirectResponse(auth_url)

async def oauth_callback(request: Request):
    """Handle GitHub callback, exchange code for token."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    
    if state not in pending_states:
        return JSONResponse({"error": "Invalid state"}, status_code=400)
    
    session_id = pending_states.pop(state)
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
            },
            headers={"Accept": "application/json"}
        )
        token_data = resp.json()
    
    access_token = token_data.get("access_token")
    if not access_token:
        return JSONResponse({"error": "Token exchange failed"}, status_code=400)
    
    # Fetch user info
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_info = user_resp.json()
    
    # Store token mapped to session
    token_store[session_id] = {
        "access_token": access_token,
        "user": user_info["login"],
        "expires_at": time.time() + 3600
    }
    
    return JSONResponse({"message": f"Authenticated as {user_info['login']}! You can close this tab."})

# ── MCP Tools ────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_my_repos",
            description="List repositories for the authenticated user",
            inputSchema={"type": "object", "properties": {}}
        ),
        types.Tool(
            name="create_issue",
            description="Create an issue in a repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["owner", "repo", "title"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    # In a real implementation, session_id comes from request context
    # Here we use a simplified version
    session_id = "current_session"
    
    token_info = token_store.get(session_id)
    if not token_info:
        return [types.TextContent(
            type="text",
            text="Not authenticated. Please visit http://localhost:8000/auth?session_id=current_session"
        )]
    
    if time.time() > token_info["expires_at"]:
        return [types.TextContent(type="text", text="Token expired. Please re-authenticate.")]
    
    access_token = token_info["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json"
    }
    
    async with httpx.AsyncClient() as client:
        if name == "list_my_repos":
            resp = await client.get("https://api.github.com/user/repos", headers=headers)
            repos = [r["full_name"] for r in resp.json()]
            return [types.TextContent(type="text", text=json.dumps(repos))]
        
        elif name == "create_issue":
            resp = await client.post(
                f"https://api.github.com/repos/{arguments['owner']}/{arguments['repo']}/issues",
                headers=headers,
                json={"title": arguments["title"], "body": arguments.get("body", "")}
            )
            data = resp.json()
            return [types.TextContent(type="text", text=f"Issue created: {data.get('html_url')}")]

# ── SSE Handler ──────────────────────────────────────────────

async def handle_sse(request: Request):
    sse = SseServerTransport("/messages/")
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await server.run(*streams, server.create_initialization_options())

app = Starlette(routes=[
    Route("/auth", oauth_authorize),
    Route("/callback", oauth_callback),
    Route("/sse", handle_sse),
    Mount("/messages/", app=SseServerTransport("/messages/").handle_post_message)
])