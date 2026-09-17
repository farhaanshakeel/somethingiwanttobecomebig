import json
import unittest
from unittest import mock

from aiohttp import web

import webapp


class DummyRequest:
    def __init__(self, path="/", query=None, cookies=None):
        self.path = path
        self.path_qs = path
        self.query = query or {}
        self.cookies = cookies or {}


class PiSpaceLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_redirects_to_login(self):
        request = DummyRequest(path="/", query={}, cookies={})

        with self.assertRaises(web.HTTPFound) as ctx:
            await webapp.handle_index(request)

        self.assertEqual(ctx.exception.location, "/login?next=%2F")

    async def test_login_page_mentions_pi_space(self):
        request = DummyRequest(path="/login", query={}, cookies={})

        response = await webapp._render_login_page(request)
        body = response.body.decode("utf-8")

        self.assertIn("Pi-space", body)
        self.assertIn("Sign in with Discord", body)

    async def test_discord_status_requires_configured_guild(self):
        original_guild_id = webapp.DISCORD_GUILD_ID
        webapp.DISCORD_GUILD_ID = ""
        try:
            response = await webapp.handle_api_discord_status(DummyRequest())
        finally:
            webapp.DISCORD_GUILD_ID = original_guild_id

        self.assertEqual(response.status, 503)
        self.assertEqual(json.loads(response.body)["available"], False)

    async def test_terms_page_is_public_and_uses_server_routes(self):
        response = await webapp.handle_terms(DummyRequest(path="/terms_and_policies.html"))
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn('href="/styles.css"', body)
        self.assertIn('src="/auth.js"', body)
        self.assertIn('href="/index.html"', body)

    async def test_public_pages_include_discord_widget(self):
        with mock.patch.object(webapp, "_current_user", new=mock.AsyncMock(return_value={"id": "1"})):
            response = await webapp.handle_activities(DummyRequest(path="/activities.html"))
        body = response.body.decode("utf-8")

        self.assertIn("discord.com/widget?id=1519982094535626862", body)

    async def test_resources_page_is_public_and_loads_resource_content(self):
        response = await webapp.handle_resources(DummyRequest(path="/resources.html"))
        body = response.body.decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("Resource library", body)
        self.assertIn("content.js", body)

    def test_forum_save_preserves_shared_data(self):
        data = {"lessons": [], "forum": {"categories": [], "threads": []}}
        with mock.patch.object(webapp, "load_data", return_value=data) as load_data:
            with mock.patch.object(webapp, "save_data") as save_data:
                forum = {"categories": ["Ideas"], "threads": [{"id": "thread-1"}]}
                webapp._save_forum(forum)

        self.assertIs(save_data.call_args.args[0], data)
        self.assertIs(data["forum"], forum)
        load_data.assert_called_once_with()

    def test_public_profile_excludes_abuse_metadata(self):
        profile = {
            "discord_id": "42",
            "display_name": "Student",
            "avatar": "avatar.png",
            "bio": "Physics learner",
            "subjects": ["Physics"],
            "private": True,
            "joined_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
            "last_ip_hash": "sensitive",
            "ip_hash_expires_at": 9999999999,
        }

        public_profile = webapp._public_profile(profile)

        self.assertNotIn("last_ip_hash", public_profile)
        self.assertNotIn("ip_hash_expires_at", public_profile)
        self.assertEqual(public_profile["private"], True)

    def test_admin_profile_excludes_network_metadata(self):
        profile = {
            "discord_id": "42",
            "display_name": "Student",
            "username": "student",
            "bio": "Physics learner",
            "subjects": ["Physics"],
            "private": True,
            "moderation_status": "review",
            "moderation_note": "Check duplicate report",
            "last_ip_hash": "sensitive",
            "ip_hash_expires_at": 9999999999,
        }

        admin_profile = webapp._admin_profile(profile)

        self.assertEqual(admin_profile["discord_id"], "42")
        self.assertEqual(admin_profile["moderation_status"], "review")
        self.assertEqual(admin_profile["moderation_note"], "Check duplicate report")
        self.assertNotIn("last_ip_hash", admin_profile)
        self.assertNotIn("ip_hash_expires_at", admin_profile)


if __name__ == "__main__":
    unittest.main()
