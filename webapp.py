"""Secure web app for the Pi-space community site.

This server handles Discord OAuth login, server-side sessions, and
authenticated delivery of the static site and lesson data.
"""

from __future__ import annotations

import html
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
from dotenv import load_dotenv

from utils import load_data, save_data


load_dotenv()


ROOT_DIR = Path(__file__).resolve().parent
SITE_DIR = ROOT_DIR / "site"
SITE_CONTENT_PATH = SITE_DIR / "content.json"

DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_ME_URL = "https://discord.com/api/users/@me"
DISCORD_GUILD_URL = "https://discord.com/api/guilds/{guild_id}?with_counts=true"
DISCORD_WIDGET_URL = "https://discord.com/api/guilds/{guild_id}/widget.json"
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "").strip()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "1519982094535626862").strip()
SITE_EDITOR_USER_ID = os.getenv("SITE_EDITOR_USER_ID", "792418858987290624").strip()
PROFILE_IP_HASH_SECRET = os.getenv("PROFILE_IP_HASH_SECRET", "").strip()
PROFILE_IP_HASH_TTL = int(os.getenv("PROFILE_IP_HASH_TTL", "2592000"))
PROFILE_UPDATE_WINDOW = int(os.getenv("PROFILE_UPDATE_WINDOW", "60"))
PROFILE_UPDATE_LIMIT = int(os.getenv("PROFILE_UPDATE_LIMIT", "10"))

SESSION_COOKIE = "tri_angle_session"
SESSION_TTL_SECONDS = int(os.getenv("SITE_SESSION_TTL", "86400"))
STATE_TTL_SECONDS = int(os.getenv("SITE_OAUTH_TTL", "300"))
COOKIE_SECURE = os.getenv(
    "SITE_COOKIE_SECURE",
    "1" if DISCORD_REDIRECT_URI.startswith("https://") else "0",
) == "1"
COOKIE_SAMESITE = os.getenv("SITE_COOKIE_SAMESITE", "Lax")
ALLOWED_CORS_ORIGINS = {
    origin.strip()
    for origin in os.getenv("SITE_CORS_ORIGINS", "").split(",")
    if origin.strip()
}

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
            "csrf_token": secrets.token_urlsafe(32),
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
PROFILE_UPDATE_ATTEMPTS: dict[str, list[float]] = {}


def _safe_next_path(value: str | None) -> str:
    if not value:
        return "/"
    if not value.startswith("/"):
        return "/"
    if "://" in value or "\\" in value:
        return "/"
    return value


def _same_origin_request(request: web.Request) -> bool:
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",", 1)[0].strip()
    expected_origin = f"{scheme}://{request.host}"
    origin = request.headers.get("Origin")
    if origin:
        return origin == expected_origin or origin in ALLOWED_CORS_ORIGINS
    referer = request.headers.get("Referer")
    return not referer or referer.startswith(f"{expected_origin}/")


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


def _client_ip(request: web.Request) -> str | None:
    if os.getenv("TRUST_PROXY", "0") != "1":
        return request.remote
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",", 1)[0].strip() or request.remote


def _ip_hash(request: web.Request) -> str | None:
    if not PROFILE_IP_HASH_SECRET:
        return None
    address = _client_ip(request)
    if not address:
        return None
    return hmac.new(
        PROFILE_IP_HASH_SECRET.encode("utf-8"), address.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _profile_for_user(user: dict, request: web.Request | None = None) -> dict:
    data = load_data()
    profiles = data.setdefault("web_profiles", {})
    user_id = str(user.get("id", ""))
    now = datetime.now(timezone.utc).isoformat()
    profile = profiles.setdefault(
        user_id,
        {
            "discord_id": user_id,
            "display_name": _display_name(user),
            "username": user.get("username", ""),
            "global_name": user.get("global_name", ""),
            "discriminator": user.get("discriminator", ""),
            "avatar": _avatar_url(user),
            "bio": "",
            "subjects": [],
            "private": True,
            "moderation_status": "normal",
            "moderation_note": "",
            "joined_at": now,
            "updated_at": now,
        },
    )
    profile["display_name"] = _display_name(user)
    profile["username"] = user.get("username", "")
    profile["global_name"] = user.get("global_name", "")
    profile["discriminator"] = user.get("discriminator", "")
    profile.setdefault("moderation_status", "normal")
    profile.setdefault("moderation_note", "")
    profile["avatar"] = _avatar_url(user)
    if request is not None:
        profile["last_seen_at"] = now
        profile["last_ip_hash"] = _ip_hash(request)
        profile["ip_hash_expires_at"] = (
            time.time() + PROFILE_IP_HASH_TTL if PROFILE_IP_HASH_SECRET else None
        )
    save_data(data)
    return profile


def _public_profile(profile: dict) -> dict:
    return {
        key: profile.get(key)
        for key in (
            "discord_id",
            "display_name",
            "avatar",
            "bio",
            "subjects",
            "private",
            "joined_at",
            "updated_at",
        )
    }


def _check_profile_update_limit(user_id: str) -> None:
    now = time.time()
    attempts = [item for item in PROFILE_UPDATE_ATTEMPTS.get(user_id, []) if item > now - PROFILE_UPDATE_WINDOW]
    if len(attempts) >= PROFILE_UPDATE_LIMIT:
        raise web.HTTPTooManyRequests(text="Too many profile updates. Try again shortly.")
    attempts.append(now)
    PROFILE_UPDATE_ATTEMPTS[user_id] = attempts


def _admin_profile(profile: dict) -> dict:
    return {
        key: profile.get(key)
        for key in (
            "discord_id",
            "display_name",
            "username",
            "global_name",
            "discriminator",
            "avatar",
            "bio",
            "subjects",
            "private",
            "joined_at",
            "updated_at",
            "last_seen_at",
            "moderation_status",
            "moderation_note",
        )
    }


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


async def _render_site_page(
    request: web.Request, page_name: str, require_auth: bool = True
) -> web.Response:
    user = await _current_user(request)
    if require_auth and user is None:
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


async def _require_editor_request(request: web.Request) -> dict:
    user = await _require_user(request)
    if not _is_site_editor(user):
        raise web.HTTPForbidden(text="Editor access required")
    if not _same_origin_request(request):
        raise web.HTTPForbidden(text="Cross-site request blocked")
    session = AUTH.get_session(request.cookies.get(SESSION_COOKIE))
    csrf_token = request.headers.get("X-CSRF-Token")
    if not session:
        raise web.HTTPForbidden(text="CSRF validation failed: session expired")
    if not csrf_token:
        raise web.HTTPForbidden(text="CSRF validation failed: token missing")
    if not secrets.compare_digest(csrf_token, session.get("csrf_token", "")):
        raise web.HTTPForbidden(text="CSRF validation failed: token expired")
    return user


async def _require_mutating_user(request: web.Request) -> dict:
    user = await _require_user(request)
    if not _same_origin_request(request):
        raise web.HTTPForbidden(text="Cross-site request blocked")
    session = AUTH.get_session(request.cookies.get(SESSION_COOKIE))
    csrf_token = request.headers.get("X-CSRF-Token")
    if not session:
        raise web.HTTPForbidden(text="CSRF validation failed: session expired")
    if not csrf_token:
        raise web.HTTPForbidden(text="CSRF validation failed: token missing")
    if not secrets.compare_digest(csrf_token, session.get("csrf_token", "")):
        raise web.HTTPForbidden(text="CSRF validation failed: token expired")
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
async def handle_resources(request: web.Request) -> web.Response:
    return await _render_site_page(request, "resources.html", require_auth=False)


async def handle_activities(request: web.Request) -> web.Response:
    return await _render_site_page(request, "activities.html")


async def handle_forum(request: web.Request) -> web.Response:
    return await _render_site_page(request, "forum.html")


async def handle_terms(request: web.Request) -> web.Response:
    return await _render_site_page(request, "terms_and_policies.html", require_auth=False)


async def handle_login(request: web.Request) -> web.Response:
    return await _render_login_page(request)


async def handle_login_start(request: web.Request) -> web.StreamResponse:
    if not DISCORD_CLIENT_ID or not DISCORD_CLIENT_SECRET or not DISCORD_REDIRECT_URI:
        raise web.HTTPInternalServerError(
            text="Discord OAuth is not configured. Set DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, and DISCORD_REDIRECT_URI."
        )

    state = AUTH.create_state("/")
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
    if not _same_origin_request(request):
        raise web.HTTPForbidden(text="Cross-site request blocked")
    session_id = request.cookies.get(SESSION_COOKIE)
    AUTH.delete_session(session_id)
    response = web.HTTPFound("/login")
    response.del_cookie(SESSION_COOKIE, path="/")
    return response


async def handle_api_discord_status(request: web.Request) -> web.Response:
    if not DISCORD_GUILD_ID:
        return web.json_response({"available": False}, status=503)

    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"} if DISCORD_BOT_TOKEN else {}
    guild_url = DISCORD_GUILD_URL.format(guild_id=DISCORD_GUILD_ID)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(guild_url, headers=headers) as guild_response:
                if guild_response.status == 200:
                    guild = await guild_response.json()
                    active_members = []
                    active_members_available = False
                    widget_url = DISCORD_WIDGET_URL.format(guild_id=DISCORD_GUILD_ID)
                    try:
                        async with session.get(widget_url) as widget_response:
                            if widget_response.status == 200:
                                widget = await widget_response.json()
                                active_members_available = True
                                active_members = [
                                    {
                                        "id": str(member.get("id", "")),
                                        "name": member.get("username", "Community member"),
                                        "avatar": member.get("avatar_url", ""),
                                        "status": member.get("status", "online"),
                                    }
                                    for member in widget.get("members", [])[:12]
                                ]
                    except (aiohttp.ClientError, TimeoutError, ValueError):
                        pass
                    return web.json_response(
                        {
                            "available": True,
                            "name": guild.get("name", "Discord server"),
                            "members": guild.get("approximate_member_count", 0),
                            "online": guild.get("approximate_presence_count", 0),
                            "activeMembers": active_members,
                            "activeMembersAvailable": active_members_available,
                        },
                        headers={"Cache-Control": "public, max-age=60"},
                    )

            widget_url = DISCORD_WIDGET_URL.format(guild_id=DISCORD_GUILD_ID)
            async with session.get(widget_url) as widget_response:
                if widget_response.status != 200:
                    return web.json_response({"available": False}, status=503)
                widget = await widget_response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return web.json_response({"available": False}, status=503)

    return web.json_response(
        {
            "available": True,
            "name": widget.get("name", "Discord server"),
            "members": len(widget.get("members", [])),
            "online": widget.get("presence_count", 0),
            "invite": widget.get("instant_invite"),
            "activeMembersAvailable": bool(widget.get("members")),
        },
        headers={"Cache-Control": "public, max-age=60"},
    )


async def handle_api_me(request: web.Request) -> web.Response:
    user = await _require_user(request)
    profile = _profile_for_user(user, request)
    return web.json_response({"user": user, "profile": _public_profile(profile)})


async def handle_api_profile(request: web.Request) -> web.Response:
    user = await _require_user(request)
    profile = _profile_for_user(user, request)
    return web.json_response({"profile": _public_profile(profile)})


async def handle_api_profile_update(request: web.Request) -> web.Response:
    user = await _require_mutating_user(request)
    _check_profile_update_limit(str(user.get("id", "")))
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="Profile must be a JSON object")

    bio = str(payload.get("bio", "")).strip()
    subjects = payload.get("subjects", [])
    private = payload.get("private", True)
    if not isinstance(subjects, list) or any(not isinstance(item, str) for item in subjects):
        raise web.HTTPBadRequest(text="Subjects must be a list of text values")
    unique_subjects = []
    seen_subjects = set()
    for item in subjects:
        subject = item.strip()
        subject_key = subject.casefold()
        if subject and subject_key not in seen_subjects:
            unique_subjects.append(subject)
            seen_subjects.add(subject_key)
    subjects = unique_subjects[:8]
    if len(bio) > 500 or any(len(item) > 60 for item in subjects):
        raise web.HTTPBadRequest(text="Profile content is too long")
    if not isinstance(private, bool):
        raise web.HTTPBadRequest(text="Private must be true or false")

    profile = _profile_for_user(user, request)
    profile["bio"] = bio
    profile["subjects"] = subjects
    profile["private"] = private
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_data(load_data())
    return web.json_response({"profile": _public_profile(profile)})


async def handle_api_public_profiles(request: web.Request) -> web.Response:
    data = load_data()
    profiles = data.get("web_profiles", {})
    public_profiles = [
        _public_profile(profile)
        for profile in profiles.values()
        if profile.get("private") is False
        and profile.get("moderation_status", "normal") == "normal"
    ]
    public_profiles.sort(key=lambda profile: profile.get("display_name", "").casefold())
    return web.json_response({"profiles": public_profiles})


async def handle_api_csrf(request: web.Request) -> web.Response:
    await _require_user(request)
    session = AUTH.get_session(request.cookies.get(SESSION_COOKIE))
    return web.json_response({"token": session["csrf_token"]})


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


def _forum_data() -> dict:
    data = load_data()
    forum = data.setdefault("forum", {"categories": [], "threads": []})
    forum.setdefault("categories", [])
    forum.setdefault("threads", [])
    return forum


def _forum_author(user: dict) -> dict:
    return {
        "id": str(user.get("id", "")),
        "name": _display_name(user),
        "avatar": _avatar_url(user),
    }


def _forum_response(forum: dict) -> dict:
    threads = sorted(
        forum.get("threads", []),
        key=lambda thread: thread.get("updated", thread.get("created", "")),
        reverse=True,
    )
    return {"categories": forum.get("categories", []), "threads": threads}


def _save_forum(forum: dict) -> None:
    data = load_data()
    data["forum"] = forum
    save_data(data)


async def handle_api_forum(request: web.Request) -> web.Response:
    await _require_user(request)
    return web.json_response(_forum_response(_forum_data()))


async def handle_api_forum_thread(request: web.Request) -> web.Response:
    user = await _require_mutating_user(request)
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")

    title = str(payload.get("title", "")).strip()
    body = str(payload.get("body", "")).strip()
    category = str(payload.get("category", "")).strip()
    if not title or not body or not category:
        raise web.HTTPBadRequest(text="Title, body, and category are required")
    if len(title) > 120 or len(body) > 5000 or len(category) > 40:
        raise web.HTTPBadRequest(text="Forum content exceeds the allowed length")

    forum = _forum_data()
    categories = {str(item).strip() for item in forum["categories"]}
    if category not in categories:
        raise web.HTTPBadRequest(text="Unknown forum category")
    now = datetime.now(timezone.utc).isoformat()
    thread = {
        "id": uuid.uuid4().hex,
        "category": category,
        "title": title,
        "created": now,
        "updated": now,
        "author": _forum_author(user),
        "replies": [{"body": body, "created": now, "author": _forum_author(user)}],
    }
    forum["threads"].append(thread)
    _save_forum(forum)
    return web.json_response({"thread": thread}, status=201)


async def handle_api_forum_reply(request: web.Request) -> web.Response:
    user = await _require_mutating_user(request)
    thread_id = request.match_info["thread_id"]
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")
    body = str(payload.get("body", "")).strip()
    if not body:
        raise web.HTTPBadRequest(text="Reply body is required")
    if len(body) > 5000:
        raise web.HTTPBadRequest(text="Reply exceeds the allowed length")

    forum = _forum_data()
    thread = next((item for item in forum["threads"] if item.get("id") == thread_id), None)
    if thread is None:
        raise web.HTTPNotFound(text="Thread not found")
    now = datetime.now(timezone.utc).isoformat()
    reply = {"body": body, "created": now, "author": _forum_author(user)}
    thread.setdefault("replies", []).append(reply)
    thread["updated"] = now
    _save_forum(forum)
    return web.json_response({"thread": thread}, status=201)


def _load_site_content() -> dict:
    try:
        return json.loads(SITE_CONTENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"brand": {}, "banner": {}, "profiles": [], "pages": {}}


async def handle_api_site_content(request: web.Request) -> web.Response:
    return web.json_response(_load_site_content())


async def handle_admin_content(request: web.Request) -> web.Response:
    await _require_editor_request(request)

    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="Content must be a JSON object")

    try:
        SITE_CONTENT_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise web.HTTPInternalServerError(text=f"Failed to save site content: {exc}")
    return web.json_response({"ok": True})


async def handle_admin_profiles(request: web.Request) -> web.Response:
    await _require_editor_request(request)
    profiles = load_data().get("web_profiles", {})
    records = sorted(
        (_admin_profile(profile) for profile in profiles.values()),
        key=lambda profile: profile.get("last_seen_at") or profile.get("joined_at") or "",
        reverse=True,
    )
    return web.json_response({"profiles": records})


async def handle_admin_profile_update(request: web.Request) -> web.Response:
    await _require_editor_request(request)
    discord_id = request.match_info["discord_id"]
    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")
    status = payload.get("moderation_status")
    note = str(payload.get("moderation_note", "")).strip()
    if status not in {"normal", "review", "restricted"}:
        raise web.HTTPBadRequest(text="Invalid moderation status")
    if len(note) > 300:
        raise web.HTTPBadRequest(text="Moderation note is too long")

    data = load_data()
    profile = data.setdefault("web_profiles", {}).get(discord_id)
    if profile is None:
        raise web.HTTPNotFound(text="Profile not found")
    profile["moderation_status"] = status
    profile["moderation_note"] = note
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_data(data)
    return web.json_response({"profile": _admin_profile(profile)})


async def handle_admin_save(request: web.Request) -> web.Response:
    """Save a site file. Only accessible to the configured site editor.

    Expects JSON: { "path": "relative/path/to/file.html", "content": "..." }
    The path is restricted to files under the project root (ROOT_DIR).
    """
    await _require_editor_request(request)

    try:
        payload = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON payload")

    path = (payload.get("path") or "").strip()
    content = payload.get("content")
    if not path or content is None:
        raise web.HTTPBadRequest(text="Missing 'path' or 'content' in payload")

    target_resolved = _resolve_site_file(path)

    # Ensure parent directories exist and write file
    try:
        target_resolved.parent.mkdir(parents=True, exist_ok=True)
        target_resolved.write_text(str(content), encoding="utf-8")
    except Exception as exc:
        raise web.HTTPInternalServerError(text=f"Failed to write file: {exc}")

    return web.json_response({"ok": True, "path": str(target_resolved.relative_to(SITE_DIR.resolve()))})


def _resolve_site_file(path: str) -> Path:
    target = ROOT_DIR / path.lstrip("/")
    try:
        target_resolved = target.resolve()
        target_resolved.relative_to(SITE_DIR.resolve())
    except Exception:
        raise web.HTTPBadRequest(text="Only files inside the site directory can be edited")
    return target_resolved


async def handle_admin_load(request: web.Request) -> web.Response:
    user = await _require_user(request)
    if not _is_site_editor(user):
        raise web.HTTPForbidden(text="Editor access required")
    target = _resolve_site_file(request.query.get("path", ""))
    if not target.is_file():
        raise web.HTTPNotFound(text="Site file not found")
    try:
        content = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise web.HTTPInternalServerError(text=f"Failed to read file: {exc}")
    return web.json_response({"path": str(target.relative_to(SITE_DIR.resolve())), "content": content})


async def handle_styles(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "styles.css")


async def handle_auth_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "auth.js")


async def handle_site_config(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "site-config.js")


async def handle_content_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "content.js")


async def handle_forum_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "forum.js")


async def handle_profile_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "profile.js")


async def handle_manifest(request: web.Request) -> web.Response:
    manifest = (SITE_DIR / "manifest.webmanifest").read_text(encoding="utf-8")
    return web.Response(text=manifest, content_type="application/manifest+json")


async def handle_pwa_script(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "pwa.js")


async def handle_service_worker(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "sw.js", headers={"Service-Worker-Allowed": "/"})


async def handle_logo(request: web.Request) -> web.Response:
    return web.FileResponse(SITE_DIR / "logo.svg")


async def handle_editor(request: web.Request) -> web.Response:
    """Serve the in-browser editor page. Only accessible to the configured site editor."""
    user = await _current_user(request)
    if not user:
        next_path = _safe_next_path(request.path_qs if request.path_qs else request.path)
        raise web.HTTPFound(f"/login?{urlencode({'next': next_path})}")

    if not _is_site_editor(user):
        raise web.HTTPForbidden(text="Editor access required")

    source_path = SITE_DIR / "editor.html"
    html_text = source_path.read_text(encoding="utf-8")
    auth_widget = _auth_widget(user)
    placeholder = '<div id="auth-widget" class="auth-slot"></div>'
    if placeholder in html_text:
        html_text = html_text.replace(placeholder, f'<div id="auth-widget" class="auth-slot">{auth_widget}</div>', 1)
    else:
        html_text = html_text.replace("</nav>", f"{auth_widget}</nav>", 1)
    return web.Response(text=html_text, content_type="text/html")


async def handle_profile(request: web.Request) -> web.Response:
    await _require_user(request)
    html_text = (SITE_DIR / "profile.html").read_text(encoding="utf-8")
    return web.Response(text=html_text, content_type="text/html")


@web.middleware
async def _cors_and_security_headers(request: web.Request, handler):
    origin = _cors_origin(request)
    if request.method == "OPTIONS" and origin:
        response = web.Response(status=204)
    else:
        response = await handler(request)

    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https: data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-src 'self' https://discord.com; "
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
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def create_app() -> web.Application:
    app = web.Application(
        client_max_size=2 * 1024 * 1024,
        middlewares=[_cors_and_security_headers],
    )

    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/lessons.html", handle_lessons)
    app.router.add_get("/resources.html", handle_resources)
    app.router.add_get("/activities.html", handle_activities)
    app.router.add_get("/forum", handle_forum)
    app.router.add_get("/forum.html", handle_forum)
    app.router.add_get("/terms_and_policies.html", handle_terms)
    app.router.add_get("/login", handle_login)
    app.router.add_get("/login/start", handle_login_start)
    app.router.add_get("/callback", handle_callback)
    app.router.add_post("/logout", handle_logout)
    app.router.add_get("/api/me", handle_api_me)
    app.router.add_get("/api/profile", handle_api_profile)
    app.router.add_put("/api/profile", handle_api_profile_update)
    app.router.add_get("/api/profiles", handle_api_public_profiles)
    app.router.add_get("/api/discord/status", handle_api_discord_status)
    app.router.add_get("/api/csrf", handle_api_csrf)
    app.router.add_get("/api/lessons", handle_api_lessons)
    app.router.add_get("/api/site-content", handle_api_site_content)
    app.router.add_get("/api/forum", handle_api_forum)
    app.router.add_post("/api/forum/threads", handle_api_forum_thread)
    app.router.add_post("/api/forum/threads/{thread_id}/replies", handle_api_forum_reply)
    app.router.add_get("/styles.css", handle_styles)
    app.router.add_get("/auth.js", handle_auth_script)
    app.router.add_get("/site-config.js", handle_site_config)
    app.router.add_get("/content.js", handle_content_script)
    app.router.add_get("/forum.js", handle_forum_script)
    app.router.add_get("/manifest.webmanifest", handle_manifest)
    app.router.add_get("/pwa.js", handle_pwa_script)
    app.router.add_get("/sw.js", handle_service_worker)
    app.router.add_get("/logo.svg", handle_logo)
    app.router.add_get("/editor", handle_editor)
    app.router.add_get("/profile", handle_profile)
    app.router.add_get("/profile.js", handle_profile_script)
    app.router.add_post("/admin/save", handle_admin_save)
    app.router.add_get("/admin/load", handle_admin_load)
    app.router.add_post("/admin/content", handle_admin_content)
    app.router.add_get("/admin/profiles", handle_admin_profiles)
    app.router.add_put("/admin/profiles/{discord_id}", handle_admin_profile_update)
    return app


app = create_app()


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host=host, port=port)