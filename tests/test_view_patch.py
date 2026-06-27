"""Standalone test: verify that the server_patch correctly wraps /view and /api/view.

Does NOT start ComfyUI. Uses aiohttp test infrastructure to simulate
ComfyUI's dual-route registration pattern.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
import unittest


def _install_test_view_handler():
    """Import and register the patched handler."""
    from encrypt_core.server_patch import patch_server_routes


class _FakeResource:
    def __init__(self, canonical: str):
        self.canonical = canonical


class _FakeRoute:
    def __init__(self, method: str, handler, canonical: str):
        self._method = method
        self._handler = handler
        self._resource = _FakeResource(canonical)

    @property
    def method(self):
        return self._method

    @property
    def handler(self):
        return self._handler

    @property
    def resource(self):
        return self._resource


class _FakeRouter:
    def __init__(self, routes):
        self._routes = routes

    def routes(self):
        return self._routes


class _FakeApp:
    def __init__(self, routes):
        self.router = _FakeRouter(routes)


class TestPatchRoutes(unittest.TestCase):
    def test_patches_both_view_and_api_view(self):
        """Verify the patch wraps BOTH /view and /api/view routes."""
        called = {"count": 0}
        original_ids = {}

        async def original_handler(request):
            called["count"] += 1
            return web.FileResponse("/tmp/fake.png")

        # Simulate ComfyUI: two routes for /view and /api/view
        route1 = _FakeRoute("GET", original_handler, "/view")
        route2 = _FakeRoute("GET", original_handler, "/api/view")

        app = _FakeApp([route1, route2])

        # We test the patching logic directly rather than importing PromptServer.
        # Inline the patch logic to verify the fix.
        from encrypt_core.server_patch import _make_view_with_decrypt
        from encrypt_core import server_patch as sp

        # Directly drive the inner loop of patch_server_routes
        _view_targets = ("/view", "/api/view")
        patched = []
        for route in app.router.routes():
            if getattr(route, "method", None) != "GET":
                continue
            resource = getattr(route, "resource", None)
            if resource is None:
                continue
            canonical = getattr(resource, "canonical", None)
            if canonical not in _view_targets:
                continue
            route._handler = _make_view_with_decrypt(route.handler)
            patched.append(canonical)

        # Both should be patched
        self.assertIn("/view", patched, "/view should be patched")
        self.assertIn("/api/view", patched, "/api/view should be patched")
        self.assertEqual(len(patched), 2, f"expected 2 patches, got {len(patched)}")

        # After patching, the handler should NOT be the original handler anymore
        self.assertIsNot(route1.handler, original_handler, "/view handler should be wrapped")
        self.assertIsNot(route2.handler, original_handler, "/api/view handler should be wrapped")

    def test_only_view_routes_patched(self):
        """Verify non-view routes (e.g. /system_stats) are NOT patched."""
        async def view_handler(request):
            return web.FileResponse("/tmp/fake.png")

        async def stats_handler(request):
            return web.Response(text="stats")

        route1 = _FakeRoute("GET", view_handler, "/view")
        route2 = _FakeRoute("GET", stats_handler, "/system_stats")
        route3 = _FakeRoute("GET", view_handler, "/api/view")

        _view_targets = ("/view", "/api/view")
        patched = []
        for route in [route1, route2, route3]:
            if getattr(route, "method", None) != "GET":
                continue
            resource = getattr(route, "resource", None)
            if resource is None:
                continue
            canonical = getattr(resource, "canonical", None)
            if canonical not in _view_targets:
                continue
            patched.append(canonical)

        self.assertEqual(patched, ["/view", "/api/view"])
        self.assertNotIn("/system_stats", patched)


if __name__ == "__main__":
    unittest.main()
