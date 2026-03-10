"""
Convenience wrappers for running tenant migrations.
"""

import os
import sys
import logging

import django
from django.core.management import execute_from_command_line

from tenantkit.tenancy.backends import get_backend

logger = logging.getLogger(__name__)


def setup_django():
    try:
        sys.path.insert(0, os.getcwd())
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
        django.setup()
        return True
    except Exception as e:
        logger.error(f"Failed to setup Django: {e}")
        return False


def run_public_migrations() -> dict:
    if not setup_django():
        return {'success': False, 'error': 'Django setup failed'}
    try:
        from tenantkit.conf import settings as tk
        if tk.TENANT_DB_MODE == 'database':
            execute_from_command_line(['manage.py', 'migrate', '--database=default'])
        else:
            execute_from_command_line(['manage.py', 'migrate_schemas', '--schema=public'])
        return {'success': True, 'message': 'Public migrations completed'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def run_tenant_migrations(tenant_name: str) -> dict:
    if not setup_django():
        return {'success': False, 'error': 'Django setup failed'}
    return get_backend().run_migrations(tenant_name)


def run_all_tenant_migrations() -> dict:
    if not setup_django():
        return {'success': False, 'error': 'Django setup failed'}
    return get_backend().run_all_migrations()


def get_all_tenants() -> list:
    return get_backend().get_all_tenants()


def run_migration_for_service(service_name: str, migration_type: str = 'all') -> dict:
    results = {}
    if migration_type in ('public', 'all'):
        results['public'] = run_public_migrations()
    if migration_type in ('tenant', 'all'):
        results['tenant'] = run_all_tenant_migrations()
    return {
        'success': all(r['success'] for r in results.values()),
        'service': service_name,
        'migration_type': migration_type,
        'results': results,
    }
