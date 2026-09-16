import unittest

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
        self.assertEqual(response.json()["available"], False)


if __name__ == "__main__":
    unittest.main()
