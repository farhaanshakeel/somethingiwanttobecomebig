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

    def test_forum_save_preserves_shared_data(self):
        data = {"lessons": [], "forum": {"categories": [], "threads": []}}
        with mock.patch.object(webapp, "load_data", return_value=data) as load_data:
            with mock.patch.object(webapp, "save_data") as save_data:
                forum = {"categories": ["Ideas"], "threads": [{"id": "thread-1"}]}
                webapp._save_forum(forum)

        self.assertIs(save_data.call_args.args[0], data)
        self.assertIs(data["forum"], forum)
        load_data.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
