"""Plugin configuration and key bootstrap."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from . import crypto

logger = logging.getLogger("ComfyUI_Encrypt_All_Pictures")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"
KEY_FILE_PATH = PLUGIN_ROOT / "encrypt_key.txt"

IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    ".avif",
    ".heic",
    ".heif",
    ".ico",
    ".ppm",
    ".pgm",
    ".pbm",
    ".pnm",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "encrypt_all_paths": False,
    "block_plaintext_writes": True,
    "comfy_managed_only": True,
}


_config: dict[str, Any] = {}


def load_config() -> dict[str, Any]:
    global _config
    merged = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.is_file():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                merged.update(json.load(f))
        except Exception as exc:
            logger.warning("Failed to read config.json: %s", exc)
    _config = merged
    return _config


def get_config() -> dict[str, Any]:
    if not _config:
        load_config()
    return _config


def is_enabled() -> bool:
    return bool(get_config().get("enabled", True))


def should_block_plaintext() -> bool:
    return bool(get_config().get("block_plaintext_writes", True))


def is_image_path(path: str | os.PathLike[str]) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def _get_comfy_roots() -> list[str]:
    roots: list[str] = []
    try:
        import folder_paths

        for getter in (
            folder_paths.get_input_directory,
            folder_paths.get_output_directory,
            folder_paths.get_temp_directory,
            folder_paths.get_user_directory,
        ):
            try:
                roots.append(os.path.abspath(getter()))
            except Exception:
                pass
    except ImportError:
        pass
    return roots


def is_managed_path(path: str | os.PathLike[str]) -> bool:
    cfg = get_config()
    abs_path = os.path.abspath(os.fspath(path))
    if cfg.get("encrypt_all_paths"):
        return True
    if not cfg.get("comfy_managed_only", True):
        return is_image_path(abs_path)
    for root in _get_comfy_roots():
        try:
            if os.path.commonpath([root, abs_path]) == root:
                return True
        except ValueError:
            continue
    return False


def should_encrypt_path(path: str | os.PathLike[str]) -> bool:
    if not is_enabled():
        return False
    if not crypto.key_configured():
        return False
    if not is_image_path(path):
        return False
    return is_managed_path(path)


def bootstrap_key() -> bool:
    env_key = os.environ.get("COMFYUI_ENCRYPT_KEY", "").strip()
    if env_key:
        try:
            crypto.set_key_from_hex(env_key)
            logger.info("Encryption key loaded from COMFYUI_ENCRYPT_KEY")
            return True
        except ValueError as exc:
            logger.error("Invalid COMFYUI_ENCRYPT_KEY: %s", exc)
            return False

    if KEY_FILE_PATH.is_file():
        try:
            content = KEY_FILE_PATH.read_text(encoding="utf-8").strip()
            if content.startswith("passphrase:"):
                salt_hex, phrase = content.split("\n", 1)
                salt = bytes.fromhex(salt_hex.split(":", 1)[1].strip())
                crypto.set_key_from_passphrase(phrase.strip(), salt=salt)
            else:
                crypto.set_key_from_hex(content)
            logger.info("Encryption key loaded from encrypt_key.txt")
            return True
        except Exception as exc:
            logger.error("Failed to load encrypt_key.txt: %s", exc)
            return False

    logger.warning(
        "No encryption key configured. Image encryption is inactive until "
        "COMFYUI_ENCRYPT_KEY or encrypt_key.txt is provided."
    )
    return False
