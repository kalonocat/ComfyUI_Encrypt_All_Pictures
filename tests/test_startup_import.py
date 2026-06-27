"""Verify prestartup and __init__ share one encrypt_core module."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class StartupImportTests(unittest.TestCase):
    def test_prestartup_and_init_share_encrypt_core(self) -> None:
        for name in list(sys.modules):
            if name == "ComfyUI_Encrypt_All_Pictures" or name.startswith(
                "ComfyUI_Encrypt_All_Pictures."
            ):
                del sys.modules[name]

        from PIL import Image

        prestartup_path = os.path.join(PLUGIN_DIR, "prestartup_script.py")
        prestartup_globals = {"__file__": prestartup_path, "__name__": "prestartup_script"}
        with open(prestartup_path, encoding="utf-8") as f:
            exec(compile(f.read(), prestartup_path, "exec"), prestartup_globals)

        prestartup_core = sys.modules["ComfyUI_Encrypt_All_Pictures.encrypt_core"]

        spec = importlib.util.spec_from_file_location(
            "ComfyUI_Encrypt_All_Pictures",
            os.path.join(PLUGIN_DIR, "__init__.py"),
            submodule_search_locations=[PLUGIN_DIR],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["ComfyUI_Encrypt_All_Pictures"] = mod
        spec.loader.exec_module(mod)

        init_core = sys.modules["ComfyUI_Encrypt_All_Pictures.encrypt_core"]

        self.assertIs(prestartup_core, init_core)
        self.assertIs(prestartup_core.crypto, init_core.crypto)
        self.assertTrue(prestartup_core.hooks._hooks_installed)
        self.assertTrue(getattr(Image.Image.save, "_ceap_hook", False))


if __name__ == "__main__":
    unittest.main()
