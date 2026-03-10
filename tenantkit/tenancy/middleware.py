"""
Tenant resolution middleware.
"""

import re
import logging

from django.http import JsonResponse
from django.db import connection, close_old_connections

from tenantkit.conf import settings as tk
from tenantkit.tenancy.context import set_current_request, clear_context
from tenantkit.tenancy.resolver import TenantResolver
from tenantkit.tenancy.backends import get_backend

logger = logging.getLogger(__name__)

_tenant_name_re = re.compile(r'^[a-z0-9_-]+$')


def _json_error(code: str, message: str, hint: str, status: int = 400):
    return JsonResponse({
        'success': False,
        'code': code,
        'error': {'message': message, 'hint': hint},
    }, status=status)


class TenantMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        self._resolver = TenantResolver()
        self._exempt = set(tk.TENANT_EXEMPT_PATHS)

    def __call__(self, request):
        clear_context()
        backend = get_backend()

        if not self._is_exempt(request.path):
            close_old_connections()
            if tk.TENANT_DB_MODE == 'schema' and hasattr(connection, 'set_schema_to_public'):
                connection.set_schema_to_public()

        set_current_request(request)

        if self._is_exempt(request.path):
            return self.get_response(request)

        tenant, tenant_name, method = self._resolver.resolve(request)

        if not tenant_name:
            if tk.REQUIRE_TENANT_BY_DEFAULT:
                return _json_error(
                    'MISSING_TENANT_HEADER',
                    'Missing X-Tenant header.',
                    'All requests must include a valid X-Tenant header.',
                )
            return self.get_response(request)

        if method == 'failed':
            return _json_error(
                'INVALID_TENANT',
                'Invalid tenant identifier.',
                'Provide a valid domain or tenant schema name.',
                status=404,
            )

        if not tenant and not _tenant_name_re.match(tenant_name):
            return _json_error(
                'INVALID_TENANT_NAME',
                'Invalid tenant name format.',
                'Tenant name must contain only lowercase letters, numbers, hyphens, and underscores.',
            )

        try:
            self._set_context(request, tenant_name, tenant, method)
            backend.activate(tenant_name)
            response = self.get_response(request)
            return response
        except Exception:
            logger.exception("Failed to activate tenant")
            return _json_error(
                'TENANT_SWITCH_ERROR',
                'Failed to switch to tenant database.',
                'Please try again or contact support.',
                status=500,
            )
        finally:
            try:
                backend.deactivate()
            except Exception:
                pass
            clear_context()

    # -- helpers ---------------------------------------------------------

    def _is_exempt(self, path: str) -> bool:
        return any(path.startswith(p) for p in self._exempt)

    @staticmethod
    def _set_context(request, tenant_name, tenant, method):
        request.tenant_name = tenant_name
        request.tenant_resolution_method = method
        if tenant:
            request.tenant = tenant
