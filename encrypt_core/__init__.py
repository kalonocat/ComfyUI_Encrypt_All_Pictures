from .config import bootstrap_key, load_config
from .hooks import install_hooks

__all__ = ["activate", "bootstrap_key", "install_hooks", "load_config"]


def activate() -> None:
    load_config()
    bootstrap_key()
    install_hooks()
