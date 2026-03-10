"""
django-tenantkit — pluggable multi-tenant toolkit for Django.

Provides schema-per-tenant and database-per-tenant backends,
tenant-scoped JWT auth, and tenant resolution middleware.

Install as a Django app:
    INSTALLED_APPS = ['tenantkit', ...]

Or import individual components:
    from tenantkit.tenancy import get_backend, TenantDatabaseRouter
    from tenantkit.auth import AuthMiddleware, TenantAuthentication
"""

from importlib import metadata as _md

try:
    __version__ = _md.version('django-tenantkit')
except Exception:
    __version__ = '0.1.0'

default_app_config = 'tenantkit.apps.TenantKitConfig'
