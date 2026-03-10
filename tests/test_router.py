"""Tests for tenantkit.tenancy.router — TenantDatabaseRouter."""

import pytest
from unittest.mock import patch, MagicMock

from tenantkit.tenancy.router import TenantDatabaseRouter
from tenantkit.tenancy.context import set_current_tenant, set_current_db_alias, clear_context


class TestTenantDatabaseRouter:

    def setup_method(self):
        clear_context()

    def teardown_method(self):
        clear_context()

    def _mock_model(self, app_label):
        model = MagicMock()
        model._meta.app_label = app_label
        return model

    def _make_router(self, tenant_apps=None, shared_apps=None, tenant_model_apps=None):
        """Create router with specific app config via patching."""
        with patch('tenantkit.tenancy.router.tk') as mock_tk:
            mock_tk.TENANT_APPS = set(tenant_apps or ['orders'])
            mock_tk.SHARED_APPS = set(shared_apps or ['contenttypes', 'sessions'])
            mock_tk.TENANT_MODEL_APPS = set(tenant_model_apps or [])
            mock_tk.TENANT_DB_MODE = 'schema'
            return TenantDatabaseRouter()

    # -- db_for_read / db_for_write --

    def test_shared_app_routes_to_default(self):
        router = self._make_router()
        model = self._mock_model('contenttypes')
        assert router.db_for_read(model) == 'default'
        assert router.db_for_write(model) == 'default'

    @patch('tenantkit.tenancy.router.get_backend')
    def test_tenant_app_routes_to_tenant_db(self, mock_backend):
        backend = MagicMock()
        backend.get_db_alias_for_current.return_value = 'tenant_acme'
        mock_backend.return_value = backend

        router = self._make_router(tenant_apps=['orders'])
        model = self._mock_model('orders')
        assert router.db_for_read(model) == 'tenant_acme'

    @patch('tenantkit.tenancy.router.get_backend')
    def test_tenant_app_raises_when_no_context(self, mock_backend):
        from tenantkit.exceptions import TenantRequiredError
        backend = MagicMock()
        backend.get_db_alias_for_current.return_value = None
        mock_backend.return_value = backend

        router = self._make_router(tenant_apps=['orders'])
        model = self._mock_model('orders')
        with pytest.raises(TenantRequiredError):
            router.db_for_read(model)

    def test_tenant_model_app_routes_to_default(self):
        router = self._make_router(tenant_model_apps=['tenancy'])
        model = self._mock_model('tenancy')
        assert router.db_for_read(model) == 'default'

    def test_unknown_app_returns_none(self):
        router = self._make_router()
        model = self._mock_model('some_unknown_app')
        assert router.db_for_read(model) is None

    # -- allow_relation --

    def test_allow_relation_same_shared_apps(self):
        router = self._make_router(shared_apps=['contenttypes', 'sessions'])
        m1 = self._mock_model('contenttypes')
        m2 = self._mock_model('sessions')
        assert router.allow_relation(m1, m2) is True

    def test_allow_relation_same_tenant_apps(self):
        router = self._make_router(tenant_apps=['orders', 'catalog'])
        m1 = self._mock_model('orders')
        m2 = self._mock_model('catalog')
        assert router.allow_relation(m1, m2) is True

    def test_allow_relation_tenant_and_shared(self):
        router = self._make_router(
            tenant_apps=['orders'],
            shared_apps=['contenttypes'],
        )
        m1 = self._mock_model('orders')
        m2 = self._mock_model('contenttypes')
        assert router.allow_relation(m1, m2) is True

    def test_allow_relation_unknown_apps(self):
        router = self._make_router()
        m1 = self._mock_model('app_a')
        m2 = self._mock_model('app_b')
        assert router.allow_relation(m1, m2) is None

    # -- allow_migrate --

    def test_shared_app_migrates_only_on_default(self):
        router = self._make_router(shared_apps=['contenttypes'])
        assert router.allow_migrate('default', 'contenttypes') is True
        assert router.allow_migrate('tenant_acme', 'contenttypes') is False

    def test_tenant_app_schema_mode_migrates_anywhere(self):
        with patch('tenantkit.tenancy.router.tk') as mock_tk:
            mock_tk.TENANT_APPS = {'orders'}
            mock_tk.SHARED_APPS = {'contenttypes'}
            mock_tk.TENANT_MODEL_APPS = set()
            mock_tk.TENANT_DB_MODE = 'schema'
            router = TenantDatabaseRouter()
            assert router.allow_migrate('default', 'orders') is True
            assert router.allow_migrate('tenant_acme', 'orders') is True

    def test_tenant_app_database_mode_not_on_default(self):
        with patch('tenantkit.tenancy.router.tk') as mock_tk:
            mock_tk.TENANT_APPS = {'orders'}
            mock_tk.SHARED_APPS = {'contenttypes'}
            mock_tk.TENANT_MODEL_APPS = set()
            mock_tk.TENANT_DB_MODE = 'database'
            router = TenantDatabaseRouter()

        with patch('tenantkit.tenancy.router.tk') as mock_tk:
            mock_tk.TENANT_DB_MODE = 'database'
            assert router.allow_migrate('default', 'orders') is False
            assert router.allow_migrate('tenant_acme', 'orders') is True

    def test_unknown_app_migrates_on_default(self):
        router = self._make_router()
        assert router.allow_migrate('default', 'some_unknown') is True
        assert router.allow_migrate('tenant_db', 'some_unknown') is False
