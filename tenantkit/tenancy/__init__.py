"""
Tenancy module — multi-tenant context, resolution, routing, and backends.
"""

from .context import (
    get_current_tenant,
    set_current_tenant,
    get_current_db_alias,
    set_current_db_alias,
    get_current_request,
    set_current_request,
    clear_context,
)
from .models import TenantMixin, DomainMixin
from .resolver import TenantResolver
from .router import TenantDatabaseRouter
from .backends import get_backend

__all__ = [
    'get_current_tenant',
    'set_current_tenant',
    'get_current_db_alias',
    'set_current_db_alias',
    'get_current_request',
    'set_current_request',
    'clear_context',
    'TenantMixin',
    'DomainMixin',
    'TenantResolver',
    'TenantDatabaseRouter',
    'get_backend',
]
