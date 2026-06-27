"""Patch ComfyUI HTTP routes so encrypted previews and uploads stay transparent."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from . import crypto
from .config import is_image_path
from .io_bypass import _original_open, bypass_encryption

logger = logging.getLogger("ComfyUI_Encrypt_All_Pictures")

_server_patched = False


def _decrypt_path_bytes(path: str) -> bytes:
    with bypass_encryption():
        with _original_open(path, "rb") as raw:
            data = raw.read()
    if crypto.is_encrypted(data):
        return crypto.decrypt_bytes(data)
    return data


def _make_view_with_decrypt(_orig: Callable[..., Any]) -> Callable[..., Any]:
    async def view_with_decrypt(request: Any) -> Any:
        response = await _orig(request)
        try:
            from aiohttp import web

            filename = request.rel_url.query.get("filename", "")
            if not filename or filename.startswith("blake3:"):
                return response

            if isinstance(response, web.FileResponse):
                path = response._path  # type: ignore[attr-defined]
                if path and os.path.isfile(path) and is_image_path(path):
                    body = _decrypt_path_bytes(path)
                    content_type = response.headers.get(
                        "Content-Type", "application/octet-stream"
                    )
                    # aiohttp forbids Content-Type in both headers dict and
                    # content_type kwarg — strip it from the copied headers.
                    headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() != "content-type"
                    }
                    return web.Response(
                        body=body, content_type=content_type, headers=headers
                    )
        except Exception as exc:
            logger.debug("View decrypt fallback: %s", exc)
        return response

    return view_with_decrypt


def patch_server_routes(force: bool = False) -> bool:
    global _server_patched

    if _server_patched and not force:
        return True

    try:
        from server import PromptServer
    except ImportError:
        return False

    if PromptServer.instance is None:
        return False

    app = PromptServer.instance.app

    # ComfyUI registers BOTH /view and /api/view (same handler, different canonical).
    # We must patch both, otherwise requests to /api/view bypass decryption.
    _view_targets = ("/view", "/api/view")
    patched_any = False
    for route in app.router.routes():
        if getattr(route, "method", None) != "GET":
            continue
        resource = getattr(route, "resource", None)
        if resource is None:
            continue
        canonical = getattr(resource, "canonical", None)
        if canonical not in _view_targets:
            continue

        route._handler = _make_view_with_decrypt(route.handler)  # type: ignore[attr-defined]
        patched_any = True
        logger.info("Patched %s route for encrypted image preview", canonical)

    if patched_any:
        _server_patched = True
    return patched_any


def schedule_server_patch() -> None:
    try:
        if patch_server_routes():
            return
    except Exception as exc:
        logger.debug("Immediate server patch failed: %s", exc)

    try:
        import asyncio
        from server import PromptServer

        async def _delayed_patch(app: Any) -> None:
            try:
                patch_server_routes(force=True)
            except Exception as exc:
                logger.warning("Deferred /view route patch failed: %s", exc)

        if PromptServer.instance is not None:
            PromptServer.instance.app.on_startup.append(_delayed_patch)
    except Exception as exc:
        logger.debug("Deferred server patch registration failed: %s", exc)
