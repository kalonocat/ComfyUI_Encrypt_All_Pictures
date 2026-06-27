"""Standalone tests for encryption hooks (no ComfyUI required)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from encrypt_core import config
from encrypt_core import crypto
from encrypt_core.config import load_config, should_encrypt_path
from encrypt_core.hooks import install_hooks
from encrypt_core.io_bypass import _original_open, bypass_encryption


class EncryptionHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        load_config()
        config._config["encrypt_all_paths"] = True
        crypto.set_key_from_hex("0123456789abcdef" * 4)
        install_hooks(force=True)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        plain = b"\x89PNG\r\n\x1a\nfake-image-bytes"
        enc = crypto.encrypt_bytes(plain)
        self.assertTrue(crypto.is_encrypted(enc))
        self.assertEqual(crypto.decrypt_bytes(enc), plain)

    def test_pil_save_and_open(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sample.png")
            self.assertTrue(should_encrypt_path(path))
            img = Image.new("RGB", (8, 8), color=(255, 0, 0))
            img.save(path)

            with _original_open(path, "rb") as f:
                on_disk = f.read()
            self.assertTrue(crypto.is_encrypted(on_disk))

            loaded = Image.open(path)
            self.assertEqual(loaded.size, (8, 8))

    def test_open_write_encrypts_on_close(self) -> None:
        """Simulates ComfyUI /upload/image: open(path, 'wb').write(bytes)."""
        plain = b"\x89PNG\r\n\x1a\nfake-upload-bytes"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "uploaded.png")
            with open(path, "wb") as writer:
                writer.write(plain)

            with _original_open(path, "rb") as f:
                on_disk = f.read()
            self.assertTrue(crypto.is_encrypted(on_disk))
            self.assertEqual(crypto.decrypt_bytes(on_disk), plain)


if __name__ == "__main__":
    unittest.main()
