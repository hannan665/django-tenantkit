"""Tests for SchemaBackend and DatabaseBackend."""

import pytest
from unittest.mock import patch, MagicMock, call

from tenantkit.tenancy.context import clear_context, get_current_tenant, get_current_db_alias
from tenantkit.tenancy.backends.schema import SchemaBackend
from tenantkit.tenancy.backends.database import DatabaseBackend
from tenantkit.tenancy.backends.base import validate_tenant_name


# ═══════════════════════════════════════════════════════════════════════
# validate_tenant_name
# ═══════════════════════════════════════════════════════════════════════

class TestValidateTenantName:

    def test_valid_names(self):
        for name in ['acme', 'tenant_acme', 'acme-corp', 'tenant123', 'a1b2c3']:
            validate_tenant_name(name)  # should not raise

    def test_empty_name_raises(self):
        with pytest.raises(ValueError):
            validate_tenant_name('')

    def test_uppercase_raises(self):
        with pytest.raises(ValueError):
            validate_tenant_name('ACME')

    def test_spaces_raise(self):
        with pytest.raises(ValueError):
            validate_tenant_name('acme corp')

    def test_special_chars_raise(self):
        with pytest.raises(ValueError):
            validate_tenant_name('acme"--drop')

    def test_semicolon_raises(self):
        with pytest.raises(ValueError):
            validate_tenant_name('acme; DROP TABLE')


# ═══════════════════════════════════════════════════════════════════════
# SchemaBackend
# ═══════════════════════════════════════════════════════════════════════

class TestSchemaBackend:

    def setup_method(self):
        clear_context()
        self.backend = SchemaBackend()

    def teardown_method(self):
        clear_context()

    def test_activate_sets_tenant_context(self):
        with patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            mock_conn.set_schema = MagicMock()
            self.backend.activate('acme')
        assert get_current_tenant() == 'acme'

    def test_activate_calls_set_schema(self):
        with patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            mock_conn.set_schema = MagicMock()
            mock_conn.set_tenant = None
            self.backend.activate('acme')
            mock_conn.set_schema.assert_called_once_with('acme')

    def test_activate_falls_back_to_set_tenant(self):
        with patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            del mock_conn.set_schema  # no set_schema attribute
            mock_conn.set_tenant = MagicMock()
            self.backend.activate('acme')
            mock_conn.set_tenant.assert_called_once()
            fake = mock_conn.set_tenant.call_args[0][0]
            assert fake.schema_name == 'acme'

    def test_activate_rejects_invalid_name(self):
        with pytest.raises(ValueError):
            self.backend.activate('INVALID NAME')

    def test_deactivate_calls_set_schema_to_public(self):
        with patch('tenantkit.tenancy.backends.schema.close_old_connections') as mock_close, \
             patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            mock_conn.set_schema_to_public = MagicMock()
            self.backend.deactivate()
            mock_close.assert_called_once()
            mock_conn.set_schema_to_public.assert_called_once()

    def test_destroy_tenant_drops_schema(self):
        mock_conn = MagicMock()
        mock_conn.ops.quote_name.return_value = '"acme"'
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        import tenantkit.tenancy.backends.schema as schema_mod
        original = schema_mod.connections
        schema_mod.connections = {'default': mock_conn}
        try:
            result = self.backend.destroy_tenant('acme')
        finally:
            schema_mod.connections = original

        assert result['success'] is True
        mock_cursor.execute.assert_called_once_with('DROP SCHEMA IF EXISTS "acme" CASCADE')

    def test_destroy_tenant_rejects_invalid_name(self):
        result = self.backend.destroy_tenant('INVALID NAME')
        assert result['success'] is False

    def test_get_db_alias_returns_default(self):
        assert self.backend.get_db_alias('acme') == 'default'

    def test_get_all_tenants(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('tenant_acme',), ('tenant_globex',)]

        with patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            tenants = self.backend.get_all_tenants()

        assert tenants == ['tenant_acme', 'tenant_globex']

    def test_get_all_tenants_on_error_returns_empty(self):
        with patch('tenantkit.tenancy.backends.schema.connection') as mock_conn:
            mock_conn.cursor.side_effect = Exception('DB error')
            result = self.backend.get_all_tenants()
        assert result == []

    def test_run_migrations_calls_execute(self):
        with patch('tenantkit.tenancy.backends.schema.execute_from_command_line') as mock_exec:
            result = self.backend.run_migrations('acme')
        assert result['success'] is True
        mock_exec.assert_called_once_with(['manage.py', 'migrate_schemas', '--schema', 'acme'])

    def test_run_migrations_on_error(self):
        with patch('tenantkit.tenancy.backends.schema.execute_from_command_line',
                   side_effect=Exception('migration failed')):
            result = self.backend.run_migrations('acme')
        assert result['success'] is False
        assert 'error' in result


# ═══════════════════════════════════════════════════════════════════════
# DatabaseBackend
# ═══════════════════════════════════════════════════════════════════════

class TestDatabaseBackend:

    def setup_method(self):
        clear_context()
        self.backend = DatabaseBackend()

    def teardown_method(self):
        clear_context()

    def test_activate_sets_tenant_and_db_alias(self):
        with patch.object(self.backend, '_ensure_registered', return_value='tenant_acme'):
            self.backend.activate('acme')
        assert get_current_tenant() == 'acme'
        assert get_current_db_alias() == 'tenant_acme'

    def test_activate_rejects_invalid_name(self):
        with pytest.raises(ValueError):
            self.backend.activate('BAD NAME!')

    def test_deactivate_calls_close_old_connections(self):
        with patch('tenantkit.tenancy.backends.database.close_old_connections') as mock_close:
            self.backend.deactivate()
            mock_close.assert_called_once()

    def test_create_tenant_returns_created_false_when_exists(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.connection.autocommit = True

        import tenantkit.tenancy.backends.database as db_mod
        original = db_mod.connections
        db_mod.connections = {'default': mock_conn}
        try:
            result = self.backend.create_tenant('acme')
        finally:
            db_mod.connections = original

        assert result['success'] is True
        assert result['created'] is False

    def test_create_tenant_creates_database(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.ops.quote_name.return_value = '"tenant_acme"'
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.connection.autocommit = False

        import tenantkit.tenancy.backends.database as db_mod
        original = db_mod.connections
        db_mod.connections = {'default': mock_conn}
        try:
            result = self.backend.create_tenant('acme')
        finally:
            db_mod.connections = original

        assert result['success'] is True
        assert result['created'] is True
        calls = mock_cursor.execute.call_args_list
        assert any('CREATE DATABASE' in str(c) for c in calls)

    def test_create_tenant_rejects_invalid_name(self):
        result = self.backend.create_tenant('BAD NAME')
        assert result['success'] is False
        assert 'error' in result

    def test_destroy_tenant_drops_database(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.ops.quote_name.return_value = '"tenant_acme"'
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.connection.autocommit = False

        import tenantkit.tenancy.backends.database as db_mod
        original = db_mod.connections
        db_mod.connections = {'default': mock_conn}
        try:
            with patch.object(self.backend, '_remove_registration') as mock_remove:
                result = self.backend.destroy_tenant('acme')
        finally:
            db_mod.connections = original

        assert result['success'] is True
        mock_remove.assert_called_once_with('acme')
        calls = mock_cursor.execute.call_args_list
        assert any('DROP DATABASE' in str(c) for c in calls)

    def test_destroy_tenant_rejects_invalid_name(self):
        result = self.backend.destroy_tenant('BAD NAME!')
        assert result['success'] is False
        assert 'error' in result

    def test_get_db_alias_returns_registered_alias(self):
        with patch.object(self.backend, '_ensure_registered', return_value='tenant_acme'):
            assert self.backend.get_db_alias('acme') == 'tenant_acme'

    def test_get_all_tenants(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [('tenant_acme',), ('tenant_globex',)]

        with patch('tenantkit.tenancy.backends.database.connection') as mock_conn:
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
            tenants = self.backend.get_all_tenants()

        assert 'acme' in tenants
        assert 'globex' in tenants

    def test_get_all_tenants_on_error_returns_empty(self):
        with patch('tenantkit.tenancy.backends.database.connection') as mock_conn:
            mock_conn.cursor.side_effect = Exception('DB error')
            result = self.backend.get_all_tenants()
        assert result == []

    def test_ensure_registered_double_check_locking(self):
        from django.conf import settings as dj_settings
        alias = 'tenant_new_tenant'
        dj_settings.DATABASES.pop(alias, None)

        with patch('tenantkit.tenancy.backends.database.tk') as mock_tk:
            mock_tk.TENANT_DB_NAME_PREFIX = 'tenant_'
            mock_tk.TENANT_DB_TEMPLATE = {}
            result = self.backend._ensure_registered('new_tenant')

        assert result == alias
        assert alias in dj_settings.DATABASES
        dj_settings.DATABASES.pop(alias, None)  # cleanup

    def test_run_migrations_calls_execute(self):
        with patch.object(self.backend, '_ensure_registered', return_value='tenant_acme'), \
             patch('tenantkit.tenancy.backends.database.execute_from_command_line') as mock_exec:
            result = self.backend.run_migrations('acme')
        assert result['success'] is True
        mock_exec.assert_called_once_with(['manage.py', 'migrate', '--database', 'tenant_acme'])

    def test_run_migrations_on_error(self):
        with patch.object(self.backend, '_ensure_registered', return_value='tenant_acme'), \
             patch('tenantkit.tenancy.backends.database.execute_from_command_line',
                   side_effect=Exception('migration failed')):
            result = self.backend.run_migrations('acme')
        assert result['success'] is False
