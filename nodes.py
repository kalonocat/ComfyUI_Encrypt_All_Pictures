"""Management nodes for encryption key and export."""

from __future__ import annotations

import os

from .encrypt_core import crypto
from .encrypt_core.config import get_config, is_image_path
from .encrypt_core.hooks import bypass_encryption
from .encrypt_core.io_bypass import _original_open


class CEAP_Status:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING", "BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("key_fingerprint", "key_ready", "encryption_enabled")
    FUNCTION = "status"
    CATEGORY = "encrypt_all_pictures"
    DESCRIPTION = "Show whether image encryption is active."

    def status(self):
        cfg = get_config()
        return (
            crypto.get_key_fingerprint() or "not configured",
            crypto.key_configured(),
            cfg.get("enabled", True) and crypto.key_configured(),
        )


class CEAP_SetKeyHex:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "hex_key": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "64 hex chars = 32-byte AES-256 key",
                    },
                )
            }
        }

    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("success", "fingerprint")
    FUNCTION = "set_key"
    CATEGORY = "encrypt_all_pictures"
    DESCRIPTION = "Set the AES-256 encryption key at runtime (hex)."

    def set_key(self, hex_key: str):
        try:
            crypto.set_key_from_hex(hex_key)
            return True, crypto.get_key_fingerprint()
        except Exception as exc:
            return False, str(exc)


class CEAP_ExportDecrypted:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "encrypted_path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Absolute path to an encrypted image on disk",
                    },
                ),
                "output_path": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Absolute path for decrypted export (plaintext PNG/JPG/etc.)",
                    },
                ),
                "overwrite": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("exported_path",)
    FUNCTION = "export"
    OUTPUT_NODE = True
    CATEGORY = "encrypt_all_pictures"
    DESCRIPTION = "Explicitly export one encrypted image to plaintext (outside enforced paths)."

    def export(self, encrypted_path: str, output_path: str, overwrite: bool = False):
        src = os.path.abspath(os.path.expanduser(encrypted_path.strip()))
        dst = os.path.abspath(os.path.expanduser(output_path.strip()))

        if not src or not os.path.isfile(src):
            raise FileNotFoundError(f"Encrypted source not found: {src}")
        if not dst:
            raise ValueError("output_path is required")
        if not is_image_path(dst):
            raise ValueError("output_path must use a standard image extension")
        if os.path.exists(dst) and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {dst}")

        os.makedirs(os.path.dirname(dst), exist_ok=True)

        with bypass_encryption():
            with _original_open(src, "rb") as f:
                data = f.read()
            if crypto.is_encrypted(data):
                data = crypto.decrypt_bytes(data)
            with _original_open(dst, "wb") as out:
                out.write(data)

        return (dst,)


NODE_CLASS_MAPPINGS = {
    "CEAP_Status": CEAP_Status,
    "CEAP_SetKeyHex": CEAP_SetKeyHex,
    "CEAP_ExportDecrypted": CEAP_ExportDecrypted,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CEAP_Status": "Encrypt Pictures - Status",
    "CEAP_SetKeyHex": "Encrypt Pictures - Set Key (Hex)",
    "CEAP_ExportDecrypted": "Encrypt Pictures - Export Decrypted",
}
