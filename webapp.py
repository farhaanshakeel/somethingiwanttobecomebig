"""Secure web app for the Pi-space community site.

This server handles Discord OAuth login, server-side sessions, and
authenticated delivery of the static site and lesson data.
"""

from __future__ import annotations

import html
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from utils import load_data


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parent
SITE_DIR = ROOT_DIR / "site"

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_ME_URL = "https://discord.com/api/users/@me"

SESSION_COOKIE = "tri_angle_session"
SESSION_TTL_SECONDS = int(os.getenv("SITE_SESSION_TTL", "86400"))
STATE_TTL_SECONDS = int(os.getenv("SITE_OAUTH_TTL", "300"))
COOKIE_SECURE = os.getenv("SITE_COOKIE_SECURE", "0") == "1"
COOKIE_SAMESITE = os.getenv("SITE_COOKIE_SAMESITE", "Lax")
ALLOWED_CORS_ORIGINS = {
    origin.strip()
    for origin in os.getenv("SITE_CORS_ORIGINS", "").split(",")
    if origin.strip()
}

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "").strip()
SITE_EDITOR_USER_ID = os.getenv("SITE_EDITOR_USER_ID", "792418858987290624").strip()


class AuthStore:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.states: dict[str, dict] = {}

    def prune(self) -> None:
        now = time.time()
        self.sessions = {
            key: value for key, value in self.sessions.items() if value["expires_at"] > now
        }
        self.states = {
            key: value for key, value in self.states.items() if value["expires_at"] > now
        }

    def create_state(self, next_path: str) -> str:
        self.prune()
        state = secrets.token_urlsafe(32)
        self.states[state] = {
            "next_path": next_path,
            "expires_at": time.time() + STATE_TTL_SECONDS,
        }
        return state

    def pop_state(self, state: str) -> dict | None:
        self.prune()
        return self.states.pop(state, None)

    def create_session(self, user: dict) -> str:
        self.prune()
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = {
            "user": user,
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        }
        return session_id

    def get_session(self, session_id: str | None) -> dict | None:
        if not session_id:
            return None
        self.prune()
        session = self.sessions.get(session_id)
        if session is None:
            return None
        if session["expires_at"] <= time.time():
            self.sessions.pop(session_id, None)
            return None
        return session

    def delete_session(self, session_id: str | None) -> None:
        if session_id:
            self.sessions.pop(session_id, None)


AUTH = AuthStore()


def _safe_next_path(value: str | None) -> str:
    if not value:
        return "/"
    if not value.startswith("/"):
        return "/"
    if "://" in value or "\\" in value:
        return "/"
    return value


def _display_name(user: dict) -> str:
    global_name = (user.get("global_name") or "").strip()
    username = user.get("username") or "Discord user"
    discriminator = user.get("discriminator")
    if global_name:
        return global_name
    if discriminator and discriminator != "0":
        return f"{username}#{discriminator}"
    return username


def _avatar_url(user: dict) -> str:
    avatar = user.get("avatar")
    user_id = user.get("id")
    if avatar and user_id:
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=64"
    return "https://cdn.discordapp.com/embed/avatars/0.png"


def _is_site_editor(user: dict | None) -> bool:
    return bool(user and SITE_EDITOR_USER_ID and str(user.get("id")) == SITE_EDITOR_USER_ID)


def _auth_widget(user: dict | None) -> str:
    if not user:
        return '<a class="auth-link auth-link-login" href="/login">Sign in with Discord</a>'

    name = html.escape(_display_name(user))
    avatar_url = html.escape(_avatar_url(user))
    editor_badge = '<span class="auth-editor-badge">Site editor</span>' if _is_site_editor(user) else ""
    return (
        '<div class="auth-widget auth-widget-signed-in">'
        '<span class="auth-status-label auth-status-label-signed-in">Signed in</span>'
        f"{editor_badge}"
        f'<div class="auth-user"><img class="auth-avatar" src="{avatar_url}" alt="Discord avatar" />'
        f'<span class="auth-name">{name}</span></div>'
        '<form action="/logout" method="post">'
        '<button class="auth-link secondary" type="submit">Sign out</button>'
        "</form>"
        "</div>"
    )


async def _current_user(request: web.Request) -> dict | None:
    session_id = request.cookies.get(SESSION_COOKIE)
    session = AUTH.get_session(session_id)
    if not session:
        return None
    return session["user"]


async def _render_site_page(request: web.Request, page_name: str) -> web.Response:
    user = await _current_user(request)
    if user is None:
        next_path = _safe_next_path(request.path_qs if request.path_qs else request.path)
        raise web.HTTPFound(f"/login?{urlencode({'next': next_path})}")

    if page_name == "terms_and_policies.html":
        source_path = ROOT_DIR / page_name
    else:
        source_path = SITE_DIR / page_name

    html_text = source_path.read_text(encoding="utf-8")
    auth_widget = _auth_widget(user)
    placeholder = '<div id="auth-widget" class="auth-slot"></div>'
    if placeholder in html_text:
        html_text = html_text.replace(placeholder, f'<div id="auth-widget" class="auth-slot">{auth_widget}</div>', 1)
    else:
        html_text = html_text.replace("</nav>", f"{auth_widget}</nav>", 1)
    return web.Response(text=html_text, content_type="text/html")


async def _render_login_page(request: web.Request) -> web.Response:
    if await _current_user(request):
        next_path = _safe_next_path(request.query.get("next"))
        raise web.HTTPFound(next_path)

    next_path = _safe_next_path(request.query.get("next"))
    login_link = "/login/start?" + urlencode({"next": next_path})
    html_text = (SITE_DIR / "login.html").read_text(encoding="utf-8")
    html_text = html_text.replace("{{LOGIN_LINK}}", html.escape(login_link))
    return web.Response(text=html_text, content_type="text/html")


async def _require_user(request: web.Request) -> dict:
    user = await _current_user(request)
    if user is None:
        raise web.HTTPUnauthorized(text="Login required")
    return user


def _cors_origin(request: web.Request) -> str | None:
    origin = request.headers.get("Origin")
    if not origin or not ALLOWED_CORS_ORIGINS:
        return None
    if origin in ALLOWED_CORS_ORIGINS:
        return origin
    return None


async def handle_index(request: web.Request) -> web.Response:
    return await _render_site_page(request, "index.html")


async def handle_lessons(request: web.Request) -> web.Response:
    return await _render_site_page(request, "lessons.html")


async def handle_activities(request: web.Request) -> web.Response:
    return await _render_site_page(request, "activities.html")


async def handle_terms(request: web.Request) -> web.Response:
    return await _render_site_page(request, "terms_and_policies.html")


async def handle_login(request: web.Request) -> web.Response:
    return await _render_login_page(request)


async def handle_login_start(request: web.Request) -> web.StreamResponse:
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not DISCORD_REDIRECT_URI:
        raise web.HTTPInternalServerError(
            text="Discord OAuth is not configured. Set DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, and DISCORD_REDIRECT_URI."
        )

    next_path = _safe_next_path(request.query.get("next"))
    state = AUTH.create_state(next_path)
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    raise web.HTTPFound(f"{DISCORD_AUTHORIZE_URL}?{urlencode(params)}")


async def handle_callback(request: web.Request) -> web.Response:
    error = request.query.get("error")
    if error:
        raise web.HTTPBadRequest(text=f"Discord login failed: {error}")

    code = request.query.get("code")
    state = request.query.get("state")
    if not code or not state:
        raise web.HTTPBadRequest(text="Missing OAuth response data")

    state_record = AUTH.pop_state(state)
    if not state_record:
        raise web.HTTPBadRequest(text="OAuth state is invalid or expired")

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        token_payload = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        }
        async with session.post(
            DISCORD_TOKEN_URL,
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as token_response:
            if token_response.status != 200:
                detail = await token_response.text()
                raise web.HTTPBadRequest(text=f"Discord token exchange failed: {detail}")
            token_data = await token_response.json()

        access_token = token_data.get("access_token")
        if not access_token:
            raise web.HTTPBadRequest(text="Discord did not return an access token")

        async with session.get(
            DISCORD_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        ) as me_response:
            if me_response.status != 200:
                detail = await me_response.text()
                raise web.HTTPBadRequest(text=f"Discord profile lookup failed: {detail}")
            user_data = await me_response.json()

    session_id = AUTH.create_session(
        {
            "id": user_data.get("id"),
            "username": user_data.get("username"),
            "discriminator": user_data.get("discriminator"),
            "global_name": user_data.get("global_name"),
            "avatar": user_data.get("avatar"),
        }
    )

    response = web.HTTPFound(state_record["next_path"])
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return response


async def handle_logout(request: web.Request) -> web.Response:
    session_id = request.cookies.get(SESSION_COOKIE)
    AUTH.delete_session(session_id)
    response = web.HTTPFound("/login")
    response.del_cookie(SESSION_COOKIE, path="/")
    return response


async def handle_api_me(request: web.Request) -> web.Response:
    user = await _require_user(request)
    return web.json_response({"user": user})


async def handle_api_lessons(request: web.Request) -> web.Response:
    await _require_user(request)
    data = load_data()
    lessons = data.get("lessons", [])
    sorted_lessons = sorted(
        lessons,
        key=lambda lesson: lesson.get("created", ""),
        reverse=True,
    )
    return web.json_response({"lessons": sorted_lessons})


async def handle_styles(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "styles.css")


async def handle_auth_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "auth.js")


async def handle_site_config(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "site-config.js")


def create_app() -> web.Application:
    app = web.Application(
        client_max_size=2 * 1024 * 1024,
        middlewares=[_cors_and_security_headers],
    )

    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/lessons.html", handle_lessons)
    app.router.add_get("/activities.html", handle_activities)
    app.router.add_get("/terms_and_policies.html", handle_terms)
    app.router.add_get("/login", handle_login)
    app.router.add_get("/login/start", handle_login_start)
    app.router.add_get("/callback", handle_callback)
    app.router.add_post("/logout", handle_logout)
    app.router.add_get("/api/me", handle_api_me)
    app.router.add_get("/api/lessons", handle_api_lessons)
    app.router.add_get("/styles.css", handle_styles)
    app.router.add_get("/auth.js", handle_auth_script)
    app.router.add_get("/site-config.js", handle_site_config)
    return app


@web.middleware
async def _cors_and_security_headers(request: web.Request, handler):
    origin = _cors_origin(request)
    if request.method == "OPTIONS" and origin:
        response = web.Response(status=204)
    else:
        response = await handler(request)

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://cdn.discordapp.com; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


if __name__ == "__main__":
    host = os.getenv("SITE_HOST", "127.0.0.1")
    port = int(os.getenv("SITE_PORT", "8080"))
    web.run_app(create_app(), host=host, port=port)