"""
Database-per-tenant backend.

Each tenant gets a dedicated PostgreSQL database. Connections are registered
dynamically in Django's DATABASES dict with thread-safe double-check locking.
"""

import logging
import threading
from typing import List

from django.conf import settings as dj_settings
from django.core.management import execute_from_command_line
from django.db import close_old_connections, connection, connections

from tenantkit.conf import settings as tk
from tenantkit.tenancy.context import set_current_tenant, set_current_db_alias
from .base import BaseTenantBackend, validate_tenant_name

logger = logging.getLogger(__name__)

_registration_lock = threading.Lock()


class DatabaseBackend(BaseTenantBackend):

    # -- public API ------------------------------------------------------

    def activate(self, tenant_name: str) -> None:
        validate_tenant_name(tenant_name)
        db_alias = self._ensure_registered(tenant_name)
        set_current_tenant(tenant_name)
        set_current_db_alias(db_alias)

    def deactivate(self) -> None:
        close_old_connections()

    def create_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        db_name = self._db_name(tenant_name)
        try:
            validate_tenant_name(tenant_name)
            conn = connections[using]
            conn.ensure_connection()
            old_ac = conn.connection.autocommit
            conn.connection.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM pg_database WHERE datname = %s", [db_name]
                    )
                    if cur.fetchone():
                        return {'success': True, 'db_name': db_name, 'created': False}
                    quoted = conn.ops.quote_name(db_name)
                    cur.execute(f'CREATE DATABASE {quoted}')
            finally:
                conn.connection.autocommit = old_ac

            logger.info("Created tenant database: %s", db_name)
            return {'success': True, 'db_name': db_name, 'created': True}
        except ValueError as e:
            logger.error("Invalid tenant name for create: %s", e)
            return {'success': False, 'db_name': db_name, 'error': str(e)}
        except Exception as e:
            logger.error("Failed to create database '%s': %s", db_name, e)
            return {'success': False, 'db_name': db_name, 'error': str(e)}

    def destroy_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        db_name = self._db_name(tenant_name)
        try:
            validate_tenant_name(tenant_name)
            self._remove_registration(tenant_name)
            conn = connections[using]
            conn.ensure_connection()
            old_ac = conn.connection.autocommit
            conn.connection.autocommit = True
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                        [db_name],
                    )
                    quoted = conn.ops.quote_name(db_name)
                    cur.execute(f'DROP DATABASE IF EXISTS {quoted}')
            finally:
                conn.connection.autocommit = old_ac

            logger.info("Dropped tenant database: %s", db_name)
            return {'success': True, 'db_name': db_name}
        except ValueError as e:
            logger.error("Invalid tenant name for destroy: %s", e)
            return {'success': False, 'db_name': db_name, 'error': str(e)}
        except Exception as e:
            logger.error("Failed to drop database '%s': %s", db_name, e)
            return {'success': False, 'db_name': db_name, 'error': str(e)}

    def run_migrations(self, tenant_name: str) -> dict:
        try:
            db_alias = self._ensure_registered(tenant_name)
            execute_from_command_line([
                'manage.py', 'migrate', '--database', db_alias,
            ])
            return {'success': True, 'tenant': tenant_name}
        except Exception as e:
            logger.error("Database migration failed for %s: %s", tenant_name, e)
            return {'success': False, 'tenant': tenant_name, 'error': str(e)}

    def run_all_migrations(self) -> dict:
        tenants = self.get_all_tenants()
        results = [{'tenant': t, **self.run_migrations(t)} for t in tenants]
        return {
            'success': all(r['success'] for r in results),
            'results': results,
        }

    def get_all_tenants(self) -> List[str]:
        prefix = tk.TENANT_DB_NAME_PREFIX
        try:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT datname FROM pg_database WHERE datname LIKE %s ORDER BY datname",
                    [f'{prefix}%'],
                )
                return [row[0][len(prefix):] for row in cur.fetchall()]
        except Exception as e:
            logger.error("Failed to list tenant databases: %s", e)
            return []

    def get_db_alias(self, tenant_name: str) -> str:
        return self._ensure_registered(tenant_name)

    # -- internal --------------------------------------------------------

    def _db_name(self, tenant_name: str) -> str:
        return f'{tk.TENANT_DB_NAME_PREFIX}{tenant_name}'

    def _ensure_registered(self, tenant_name: str) -> str:
        db_alias = self._db_name(tenant_name)
        if db_alias in dj_settings.DATABASES:
            return db_alias

        with _registration_lock:
            if db_alias in dj_settings.DATABASES:
                return db_alias

            template = tk.TENANT_DB_TEMPLATE
            default_db = dj_settings.DATABASES.get('default', {})
            config = {**default_db, **template, 'NAME': db_alias}
            dj_settings.DATABASES[db_alias] = config
            logger.info("Registered tenant database: %s", db_alias)

        return db_alias

    def _remove_registration(self, tenant_name: str) -> None:
        db_alias = self._db_name(tenant_name)
        with _registration_lock:
            dj_settings.DATABASES.pop(db_alias, None)
