from .encrypt_core import activate
from .encrypt_core.server_patch import schedule_server_patch
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

activate()
schedule_server_patch()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
