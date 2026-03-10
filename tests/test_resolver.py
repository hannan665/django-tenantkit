"""Tests for tenantkit.tenancy.resolver — TenantResolver."""

import pytest
from unittest.mock import patch, MagicMock

from django.test import RequestFactory

from tenantkit.tenancy.resolver import TenantResolver


class TestTenantResolver:

    def setup_method(self):
        self.resolver = TenantResolver()

    def test_no_header_no_domain_returns_none(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')

        with patch.object(self.resolver, '_resolve_domain', return_value=(None, None)):
            tenant, schema, method = self.resolver.resolve(request)

        assert tenant is None
        assert schema is None
        assert method is None

    def test_x_tenant_header_domain_lookup(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='acme.example.com')

        mock_tenant = MagicMock()
        mock_tenant.schema_name = 'tenant_acme'

        with patch.object(self.resolver, '_lookup_domain',
                         return_value=(mock_tenant, 'tenant_acme')):
            tenant, schema, method = self.resolver.resolve(request)

        assert tenant is mock_tenant
        assert schema == 'tenant_acme'
        assert method == 'x-tenant-domain'

    def test_x_tenant_header_schema_lookup_fallback(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        mock_tenant = MagicMock()
        mock_tenant.schema_name = 'tenant_acme'

        with patch.object(self.resolver, '_lookup_domain', return_value=(None, None)):
            with patch.object(self.resolver, '_lookup_schema',
                             return_value=(mock_tenant, 'tenant_acme')):
                tenant, schema, method = self.resolver.resolve(request)

        assert tenant is mock_tenant
        assert schema == 'tenant_acme'
        assert method == 'x-tenant-schema'

    def test_x_tenant_header_not_found(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='nonexistent')

        with patch.object(self.resolver, '_lookup_domain', return_value=(None, None)):
            with patch.object(self.resolver, '_lookup_schema', return_value=(None, None)):
                tenant, schema, method = self.resolver.resolve(request)

        assert tenant is None
        assert schema == 'nonexistent'
        assert method == 'failed'

    def test_host_domain_resolution(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_HOST='acme.example.com')

        mock_tenant = MagicMock()
        mock_tenant.schema_name = 'tenant_acme'

        with patch.object(self.resolver, '_lookup_domain',
                         return_value=(mock_tenant, 'tenant_acme')):
            tenant, schema, method = self.resolver.resolve(request)

        assert tenant is mock_tenant
        assert method == 'domain'

    def test_header_case_insensitive(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='TENANT_ACME')

        mock_tenant = MagicMock()
        with patch.object(self.resolver, '_lookup_domain', return_value=(None, None)):
            with patch.object(self.resolver, '_lookup_schema',
                             return_value=(mock_tenant, 'tenant_acme')):
                tenant, schema, method = self.resolver.resolve(request)

        assert tenant is mock_tenant

    def test_header_trimmed(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='  tenant_acme  ')

        mock_tenant = MagicMock()
        with patch.object(self.resolver, '_lookup_domain', return_value=(None, None)):
            with patch.object(self.resolver, '_lookup_schema',
                             return_value=(mock_tenant, 'tenant_acme')):
                tenant, schema, method = self.resolver.resolve(request)

        assert tenant is mock_tenant

    @patch('tenantkit.tenancy.resolver.tk')
    def test_fallback_disabled_skips_header(self, mock_tk):
        mock_tk.TENANT_RESOLUTION_FALLBACK_ENABLED = False
        mock_tk.TENANT_HEADER_NAME = 'X-Tenant'

        resolver = TenantResolver()
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        with patch.object(resolver, '_resolve_domain', return_value=(None, None)):
            tenant, schema, method = resolver.resolve(request)

        assert tenant is None
        assert schema is None
