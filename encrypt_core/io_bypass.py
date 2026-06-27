"""Low-level I/O bypass helpers to avoid recursive hook calls."""

from __future__ import annotations

import builtins
import threading
from typing import Any, Callable

_original_open: Callable[..., Any] = builtins.open
_bypass = threading.local()


def in_bypass() -> bool:
    return bool(getattr(_bypass, "active", False))


class bypass_encryption:
    def __enter__(self) -> "bypass_encryption":
        self._prev = getattr(_bypass, "active", False)
        _bypass.active = True
        return self

    def __exit__(self, *args: object) -> None:
        _bypass.active = self._prev


def capture_original_open() -> None:
    global _original_open
    _original_open = builtins.open
