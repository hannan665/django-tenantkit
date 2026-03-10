"""
Backend factory — returns the correct tenant backend based on TENANT_DB_MODE.
"""

from tenantkit.conf import settings as tk

_backend = None


def get_backend():
    """Return a singleton tenant backend instance."""
    global _backend
    if _backend is None:
        mode = tk.TENANT_DB_MODE
        if mode == 'database':
            from .database import DatabaseBackend
            _backend = DatabaseBackend()
        else:
            from .schema import SchemaBackend
            _backend = SchemaBackend()
    return _backend
