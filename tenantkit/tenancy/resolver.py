"""
Tenant resolution from HTTP requests.

Supports X-Tenant header (domain or schema_name lookup) and host domain resolution.
"""

import logging
from typing import Any, Optional, Tuple

from tenantkit.conf import settings as tk

logger = logging.getLogger(__name__)


class TenantResolver:
    """Resolve a tenant object and schema_name from an incoming request."""

    def resolve(self, request) -> Tuple[Any, Optional[str], Optional[str]]:
        """
        Resolve tenant from request.

        Priority:
            1. X-Tenant header (domain lookup, then schema_name lookup)
            2. Host domain resolution

        Returns:
            (tenant_obj | None, schema_name | None, resolution_method | None)
            resolution_method: 'x-tenant-domain' | 'x-tenant-schema' | 'domain' | 'failed' | None
        """
        fallback_enabled = tk.TENANT_RESOLUTION_FALLBACK_ENABLED
        header_name = tk.TENANT_HEADER_NAME
        x_tenant = (
            request.headers.get(header_name, '').strip().lower()
            if fallback_enabled else ''
        )

        if x_tenant:
            tenant, schema, method = self._resolve_header(x_tenant)
            if tenant:
                return tenant, schema, method
            return None, x_tenant, 'failed'

        # Fallback to host domain
        tenant, schema = self._resolve_domain(request)
        if tenant:
            return tenant, schema, 'domain'

        return None, None, None

    # -- internal ---------------------------------------------------------

    def _resolve_header(self, value: str) -> Tuple[Any, Optional[str], Optional[str]]:
        """Try domain lookup first, then schema_name lookup."""
        tenant, schema = self._lookup_domain(value)
        if tenant:
            return tenant, schema, 'x-tenant-domain'

        tenant, schema = self._lookup_schema(value)
        if tenant:
            return tenant, schema, 'x-tenant-schema'

        return None, None, None

    def _resolve_domain(self, request) -> Tuple[Any, Optional[str]]:
        host = request.get_host()
        domain = host.split(':')[0] if ':' in host else host
        return self._lookup_domain(domain)

    def _lookup_domain(self, domain: str) -> Tuple[Any, Optional[str]]:
        from django.apps import apps

        try:
            app_label, model_name = tk.TENANT_DOMAIN_MODEL.rsplit('.', 1)
            Domain = apps.get_model(app_label, model_name)
            domain_obj = Domain.objects.select_related('tenant').get(domain=domain)
            return domain_obj.tenant, domain_obj.tenant.schema_name
        except Exception:
            return None, None

    def _lookup_schema(self, schema_name: str) -> Tuple[Any, Optional[str]]:
        from django.apps import apps

        try:
            app_label, model_name = tk.TENANT_MODEL.rsplit('.', 1)
            Tenant = apps.get_model(app_label, model_name)
            tenant = Tenant.objects.get(schema_name=schema_name)
            return tenant, tenant.schema_name
        except Exception:
            return None, None
