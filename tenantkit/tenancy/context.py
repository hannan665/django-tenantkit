"""
Tenant context storage using contextvars.

Stores the current tenant name, database alias, and request per-task/thread.
Uses contextvars instead of threading.local for ASGI/async compatibility.
"""

import contextvars
from typing import Optional

_tenant_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('tenant_name', default=None)
_db_alias: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('db_alias', default=None)
_request: contextvars.ContextVar = contextvars.ContextVar('request', default=None)


def set_current_tenant(tenant_name: str):
    _tenant_name.set(tenant_name)


def get_current_tenant() -> Optional[str]:
    return _tenant_name.get()


def set_current_db_alias(db_alias: str):
    _db_alias.set(db_alias)


def get_current_db_alias() -> Optional[str]:
    return _db_alias.get()


def set_current_request(request):
    _request.set(request)


def get_current_request():
    return _request.get()


def clear_context():
    _tenant_name.set(None)
    _db_alias.set(None)
    _request.set(None)
