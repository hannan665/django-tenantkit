"""
Shared test fixtures and Django settings for tenantkit tests.

These tests are unit tests that mock database/schema operations.
No real PostgreSQL connection is required.
"""

import os
import django
from django.conf import settings

# Minimal Django settings for testing
if not settings.configured:
    settings.configure(
        SECRET_KEY='test-secret-key-for-tenantkit',
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
        ],
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        DEFAULT_AUTO_FIELD='django.db.models.BigAutoField',
        ALLOWED_HOSTS=['*'],
        # Tenantkit settings
        TENANT_DB_MODE='schema',
        TENANT_MODEL='auth.User',  # dummy for tests
        TENANT_DOMAIN_MODEL='auth.User',  # dummy for tests
        TENANT_APPS=['auth'],
        SHARED_APPS=['contenttypes', 'auth', 'sessions'],
        TENANT_HEADER_NAME='X-Tenant',
        REQUIRE_TENANT_BY_DEFAULT=True,
        REQUIRE_AUTH_BY_DEFAULT=True,
        JWT_ALGORITHM='HS256',
        AUTH_CACHE_TIMEOUT=0,  # disable caching in tests
        TENANT_USER_APP_LABEL='auth',
        TENANT_USER_MODEL_NAME='User',
        TENANT_EXEMPT_PATHS=['/health/', '/admin/'],
        AUTH_EXEMPT_PATHS=['/health/', '/admin/'],
        AUTH_OPTIONAL_PATHS=['/api/optional/'],
        PUBLIC_GET_ENDPOINTS=['/api/public/'],
        CUSTOMER_SOURCE_REQUIRED_ENDPOINTS=[],
        TENANT_RESOLUTION_FALLBACK_ENABLED=True,
    )
    django.setup()
