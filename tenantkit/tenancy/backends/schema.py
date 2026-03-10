"""
Schema-per-tenant backend (uses django-tenants under the hood).
"""

import logging
from typing import List

from django.core.management import execute_from_command_line
from django.db import connection, connections, close_old_connections

from tenantkit.tenancy.context import set_current_tenant
from .base import BaseTenantBackend, validate_tenant_name

logger = logging.getLogger(__name__)


class _FakeTenant:
    """Minimal tenant object accepted by django-tenants' set_tenant."""
    def __init__(self, schema_name: str):
        self.schema_name = schema_name


class SchemaBackend(BaseTenantBackend):

    def activate(self, tenant_name: str) -> None:
        validate_tenant_name(tenant_name)
        set_current_tenant(tenant_name)
        if hasattr(connection, 'set_schema'):
            connection.set_schema(tenant_name)
        elif hasattr(connection, 'set_tenant'):
            connection.set_tenant(_FakeTenant(tenant_name))

    def deactivate(self) -> None:
        close_old_connections()
        if hasattr(connection, 'set_schema_to_public'):
            connection.set_schema_to_public()

    def create_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        # In schema mode the schema is created by django-tenants on Tenant.save().
        # We just run migrations afterward.
        return self.run_migrations(tenant_name)

    def destroy_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        try:
            validate_tenant_name(tenant_name)
            conn = connections[using]
            conn.ensure_connection()
            quoted = conn.ops.quote_name(tenant_name)
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS {quoted} CASCADE')
            logger.info("Dropped schema: %s", tenant_name)
            return {'success': True, 'schema': tenant_name}
        except ValueError as e:
            logger.error("Invalid tenant name for destroy: %s", e)
            return {'success': False, 'schema': tenant_name, 'error': str(e)}
        except Exception as e:
            logger.error("Failed to drop schema '%s': %s", tenant_name, e)
            return {'success': False, 'schema': tenant_name, 'error': str(e)}

    def run_migrations(self, tenant_name: str) -> dict:
        try:
            execute_from_command_line([
                'manage.py', 'migrate_schemas', '--schema', tenant_name,
            ])
            return {'success': True, 'tenant': tenant_name}
        except Exception as e:
            logger.error("Schema migration failed for %s: %s", tenant_name, e)
            return {'success': False, 'tenant': tenant_name, 'error': str(e)}

    def run_all_migrations(self) -> dict:
        tenants = self.get_all_tenants()
        results = [{'tenant': t, **self.run_migrations(t)} for t in tenants]
        return {
            'success': all(r['success'] for r in results),
            'results': results,
        }

    def get_all_tenants(self) -> List[str]:
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT nspname FROM pg_catalog.pg_namespace "
                    "WHERE nspname LIKE 'tenant_%%' ORDER BY nspname"
                )
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logger.error("Failed to list tenant schemas: %s", e)
            return []

    def get_db_alias(self, tenant_name: str) -> str:
        return 'default'
