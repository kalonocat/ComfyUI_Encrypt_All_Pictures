"""Install encryption hooks as early as possible during ComfyUI startup."""

from __future__ import annotations

import importlib
import os
import sys
import types

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
PKG_NAME = os.path.basename(PLUGIN_DIR)

# Register the plugin package namespace so prestartup and __init__.py share one
# encrypt_core module (avoid duplicate hooks / split crypto key state).
if PKG_NAME not in sys.modules:
    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [PLUGIN_DIR]
    pkg.__package__ = PKG_NAME
    sys.modules[PKG_NAME] = pkg

importlib.import_module(f"{PKG_NAME}.encrypt_core").activate()
