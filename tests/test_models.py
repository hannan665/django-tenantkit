"""Tests for tenantkit.tenancy.models — TenantMixin save/delete behavior."""

import pytest
from unittest.mock import patch, MagicMock

from tenantkit.tenancy.models import TenantMixin, DomainMixin


class TestTenantMixinSave:

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_schema_mode_delegates_to_parent(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'schema'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = True
            tenant._state = MagicMock()
            tenant._state.adding = True
            TenantMixin.save(tenant, verbosity=1)
            mock_parent_save.assert_called_once()

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_database_mode_creates_database(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = True
            tenant.schema_name = 'tenant_acme'
            tenant._state = MagicMock()
            tenant._state.adding = True

            mock_backend = MagicMock()
            mock_backend.create_tenant.return_value = {'success': True}
            mock_backend.run_migrations.return_value = {'success': True}

            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.save(tenant, verbosity=1)

            mock_parent_save.assert_called_once()
            mock_backend.create_tenant.assert_called_once_with('tenant_acme')
            mock_backend.run_migrations.assert_called_once_with('tenant_acme')

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_database_mode_skips_create_on_update(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = True
            tenant.schema_name = 'tenant_acme'
            tenant._state = MagicMock()
            tenant._state.adding = False

            mock_backend = MagicMock()
            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.save(tenant, verbosity=1)
                mock_backend.create_tenant.assert_not_called()

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_database_mode_rollback_on_create_failure(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = True
            tenant.schema_name = 'tenant_fail'
            tenant._state = MagicMock()
            tenant._state.adding = True

            mock_backend = MagicMock()
            mock_backend.create_tenant.return_value = {
                'success': False, 'error': 'disk full'
            }

            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                with pytest.raises(Exception, match='Failed to create tenant database'):
                    TenantMixin.save(tenant, verbosity=1)

            tenant.delete.assert_called_once_with(force_drop=True)

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_database_mode_rollback_on_migration_failure(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = True
            tenant.schema_name = 'tenant_migfail'
            tenant._state = MagicMock()
            tenant._state.adding = True

            mock_backend = MagicMock()
            mock_backend.create_tenant.return_value = {'success': True}
            mock_backend.run_migrations.return_value = {
                'success': False, 'error': 'migration error'
            }

            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                with pytest.raises(Exception, match='Migrations failed'):
                    TenantMixin.save(tenant, verbosity=1)

            # Both database and row should be cleaned up
            mock_backend.destroy_tenant.assert_called_once_with('tenant_migfail')
            tenant.delete.assert_called_once_with(force_drop=True)

    @patch('tenantkit.tenancy.models.BaseTenantMixin.save')
    def test_database_mode_auto_create_disabled(self, mock_parent_save):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_create_schema = False
            tenant.schema_name = 'tenant_manual'
            tenant._state = MagicMock()
            tenant._state.adding = True

            mock_backend = MagicMock()
            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.save(tenant, verbosity=1)
                mock_backend.create_tenant.assert_not_called()


class TestTenantMixinDelete:

    @patch('tenantkit.tenancy.models.BaseTenantMixin.delete')
    def test_schema_mode_delegates_to_parent(self, mock_parent_delete):
        with patch('django.conf.settings.TENANT_DB_MODE', 'schema'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_drop_schema = True
            TenantMixin.delete(tenant, force_drop=True)
            mock_parent_delete.assert_called_once()

    @patch('tenantkit.tenancy.models.BaseTenantMixin.delete')
    def test_database_mode_drops_database(self, mock_parent_delete):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_drop_schema = True
            tenant.schema_name = 'tenant_acme'

            mock_backend = MagicMock()
            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.delete(tenant, force_drop=False)

            mock_backend.destroy_tenant.assert_called_once_with('tenant_acme')
            mock_parent_delete.assert_called_once()

    @patch('tenantkit.tenancy.models.BaseTenantMixin.delete')
    def test_database_mode_no_drop_without_flag(self, mock_parent_delete):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_drop_schema = False
            tenant.schema_name = 'tenant_acme'

            mock_backend = MagicMock()
            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.delete(tenant, force_drop=False)
                mock_backend.destroy_tenant.assert_not_called()

    @patch('tenantkit.tenancy.models.BaseTenantMixin.delete')
    def test_database_mode_force_drop(self, mock_parent_delete):
        with patch('django.conf.settings.TENANT_DB_MODE', 'database'):
            tenant = MagicMock(spec=TenantMixin)
            tenant.auto_drop_schema = False
            tenant.schema_name = 'tenant_acme'

            mock_backend = MagicMock()
            with patch('tenantkit.tenancy.backends.get_backend', return_value=mock_backend):
                TenantMixin.delete(tenant, force_drop=True)

            mock_backend.destroy_tenant.assert_called_once_with('tenant_acme')
