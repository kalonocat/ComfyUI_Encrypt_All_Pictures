"""Global I/O hooks that force encrypted image disk writes."""

from __future__ import annotations

import builtins
import io
import logging
import os
from typing import Any, Callable, Optional

from . import crypto
from .config import is_image_path, should_encrypt_path
from .io_bypass import _original_open, bypass_encryption, capture_original_open, in_bypass

logger = logging.getLogger("ComfyUI_Encrypt_All_Pictures")

_hooks_installed = False
_original_image_save: Optional[Callable[..., Any]] = None
_original_image_open: Optional[Callable[..., Any]] = None
_original_cv2_imwrite: Optional[Callable[..., Any]] = None
_original_cv2_imread: Optional[Callable[..., Any]] = None


class _EncryptingWriter:
    """Buffer image writes and encrypt on close."""

    def __init__(self, path: str):
        self._path = path
        self._buffer = bytearray()
        self.closed = False

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self.closed:
            raise ValueError("I/O operation on closed file")
        chunk = bytes(data)
        self._buffer.extend(chunk)
        return len(chunk)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        with bypass_encryption():
            crypto.write_encrypted_file(self._path, bytes(self._buffer))

    def __enter__(self) -> "_EncryptingWriter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class _DecryptingReader:
    """Serve decrypted bytes for encrypted image files."""

    def __init__(self, path: str):
        with bypass_encryption():
            with _original_open(path, "rb") as raw:
                data = raw.read()
        if crypto.is_encrypted(data):
            data = crypto.decrypt_bytes(data)
        self._stream = io.BytesIO(data)
        self.name = path
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def readinto(self, b: bytearray) -> int:
        return self._stream.readinto(b)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._stream.seek(offset, whence)

    def tell(self) -> int:
        return self._stream.tell()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        chunk = self.read(8192)
        if not chunk:
            raise StopIteration
        return chunk

    def close(self) -> None:
        self.closed = True
        self._stream.close()

    def __enter__(self) -> "_DecryptingReader":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _normalize_open_path(file: Any) -> Optional[str]:
    if isinstance(file, (str, os.PathLike)):
        return os.fspath(file)
    if hasattr(file, "name") and isinstance(file.name, str) and file.name not in ("", "<stdin>", "<stdout>"):
        return file.name
    return None


def _patched_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    if in_bypass():
        return _original_open(file, mode, *args, **kwargs)

    path = _normalize_open_path(file)
    if path and should_encrypt_path(path):
        mode_set = set(mode.replace("+", ""))
        if "w" in mode_set or "a" in mode_set or "x" in mode_set:
            if "b" not in mode_set and "t" in mode_set:
                raise TypeError("Encrypted image writes must use binary mode")
            return _EncryptingWriter(path)
        if "r" in mode_set and "b" in mode_set:
            with bypass_encryption():
                with _original_open(path, "rb") as probe:
                    header = probe.read(len(crypto.MAGIC))
            if header == crypto.MAGIC:
                return _DecryptingReader(path)

    return _original_open(file, mode, *args, **kwargs)


_patched_open._ceap_hook = True  # type: ignore[attr-defined]


def _patched_image_save(self: Any, fp: Any, format: Optional[str] = None, **params: Any) -> None:
    assert _original_image_save is not None
    if in_bypass():
        return _original_image_save(self, fp, format=format, **params)

    target_path = _normalize_open_path(fp)
    if target_path and should_encrypt_path(target_path):
        if format is None:
            ext = os.path.splitext(target_path)[1].lower()
            format = {
                ".png": "PNG",
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".webp": "WEBP",
                ".bmp": "BMP",
                ".tif": "TIFF",
                ".tiff": "TIFF",
                ".gif": "GIF",
            }.get(ext, ext.lstrip(".").upper() or "PNG")
        buffer = io.BytesIO()
        _original_image_save(self, buffer, format=format, **params)
        with bypass_encryption():
            crypto.write_encrypted_file(target_path, buffer.getvalue())
        return

    return _original_image_save(self, fp, format=format, **params)


_patched_image_save._ceap_hook = True  # type: ignore[attr-defined]


def _patched_image_open(fp: Any, mode: str = "r", formats: Any = None) -> Any:
    assert _original_image_open is not None
    if in_bypass():
        return _original_image_open(fp, mode=mode, formats=formats)

    path = _normalize_open_path(fp)
    if path and is_image_path(path) and os.path.isfile(path):
        with bypass_encryption():
            with _original_open(path, "rb") as raw:
                data = raw.read()
        if crypto.is_encrypted(data):
            data = crypto.decrypt_bytes(data)
            return _original_image_open(io.BytesIO(data), mode=mode, formats=formats)

    return _original_image_open(fp, mode=mode, formats=formats)


_patched_image_open._ceap_hook = True  # type: ignore[attr-defined]


def _patched_cv2_imwrite(filename: str, img: Any, *args: Any, **kwargs: Any) -> bool:
    assert _original_cv2_imwrite is not None
    if should_encrypt_path(filename):
        import cv2

        ext = os.path.splitext(filename)[1]
        ok, encoded = cv2.imencode(ext if ext else ".png", img)
        if not ok:
            return False
        with bypass_encryption():
            crypto.write_encrypted_file(filename, encoded.tobytes())
        return True
    return _original_cv2_imwrite(filename, img, *args, **kwargs)


def _patched_cv2_imread(filename: str, flags: int = -1) -> Any:
    assert _original_cv2_imread is not None
    if is_image_path(filename) and os.path.isfile(filename):
        with bypass_encryption():
            with _original_open(filename, "rb") as raw:
                data = raw.read()
        if crypto.is_encrypted(data):
            import cv2
            import numpy as np

            data = crypto.decrypt_bytes(data)
            arr = np.frombuffer(data, dtype=np.uint8)
            return cv2.imdecode(arr, flags)
    return _original_cv2_imread(filename, flags)


_patched_cv2_imwrite._ceap_hook = True  # type: ignore[attr-defined]
_patched_cv2_imread._ceap_hook = True  # type: ignore[attr-defined]


def _hooks_already_active() -> bool:
    from PIL import Image

    open_hooked = getattr(builtins.open, "_ceap_hook", False)
    save_hooked = getattr(Image.Image.save, "_ceap_hook", False)
    pil_open_hooked = getattr(Image.open, "_ceap_hook", False)
    return open_hooked or save_hooked or pil_open_hooked


def install_hooks(force: bool = False) -> bool:
    global _hooks_installed, _original_image_save, _original_image_open
    global _original_cv2_imwrite, _original_cv2_imread

    if (_hooks_installed or _hooks_already_active()) and not force:
        _hooks_installed = True
        return True

    from PIL import Image

    if not getattr(builtins.open, "_ceap_hook", False):
        if _original_open is builtins.open:
            capture_original_open()
        builtins.open = _patched_open

    if _original_image_save is None and not getattr(Image.Image.save, "_ceap_hook", False):
        _original_image_save = Image.Image.save
        Image.Image.save = _patched_image_save  # type: ignore[method-assign]

    if _original_image_open is None and not getattr(Image.open, "_ceap_hook", False):
        _original_image_open = Image.open
        Image.open = _patched_image_open  # type: ignore[assignment]

    try:
        import cv2

        if _original_cv2_imwrite is None and not getattr(cv2.imwrite, "_ceap_hook", False):
            _original_cv2_imwrite = cv2.imwrite
            cv2.imwrite = _patched_cv2_imwrite  # type: ignore[assignment]
        if _original_cv2_imread is None and not getattr(cv2.imread, "_ceap_hook", False):
            _original_cv2_imread = cv2.imread
            cv2.imread = _patched_cv2_imread  # type: ignore[assignment]
    except ImportError:
        pass

    _hooks_installed = True
    logger.info("Image encryption hooks installed (PIL/cv2/open)")
    return True
