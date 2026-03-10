"""
Centralized configuration for tenantkit.

Every property reads from Django ``settings`` with a sensible default.

    from tenantkit.conf import settings as tk
    print(tk.TENANT_DB_MODE)   # 'schema'
"""

from django.conf import settings as _dj


class _Settings:

    # -- Tenancy ---------------------------------------------------------------

    @property
    def TENANT_DB_MODE(self) -> str:
        """``'schema'`` (default) or ``'database'``."""
        return getattr(_dj, 'TENANT_DB_MODE', 'schema')

    @property
    def TENANT_DB_NAME_PREFIX(self) -> str:
        return getattr(_dj, 'TENANT_DB_NAME_PREFIX', 'tenant_')

    @property
    def TENANT_DB_TEMPLATE(self) -> dict:
        return getattr(_dj, 'TENANT_DB_TEMPLATE', {})

    @property
    def TENANT_MODEL(self) -> str:
        return getattr(_dj, 'TENANT_MODEL', 'tenancy.Tenant')

    @property
    def TENANT_DOMAIN_MODEL(self) -> str:
        return getattr(_dj, 'TENANT_DOMAIN_MODEL', 'tenancy.Domain')

    @property
    def TENANT_HEADER_NAME(self) -> str:
        return getattr(_dj, 'TENANT_HEADER_NAME', 'X-Tenant')

    @property
    def REQUIRE_TENANT_BY_DEFAULT(self) -> bool:
        return getattr(_dj, 'REQUIRE_TENANT_BY_DEFAULT', True)

    @property
    def TENANT_EXEMPT_PATHS(self) -> list:
        return getattr(_dj, 'TENANT_EXEMPT_PATHS', [
            '/health/', '/metrics/', '/docs/', '/admin/',
            '/api/public/', '/schema/',
        ])

    @property
    def PUBLIC_SCHEMA_NAME(self) -> str:
        return getattr(_dj, 'PUBLIC_SCHEMA_NAME', 'public')

    @property
    def TENANT_APPS(self) -> set:
        return set(getattr(_dj, 'TENANT_APPS', []))

    @property
    def SHARED_APPS(self) -> set:
        return set(getattr(_dj, 'SHARED_APPS', []))

    @property
    def TENANT_MODEL_APPS(self) -> set:
        return set(getattr(_dj, 'TENANT_MODEL_APPS', []))

    @property
    def TENANT_RESOLUTION_FALLBACK_ENABLED(self) -> bool:
        return getattr(_dj, 'TENANT_RESOLUTION_FALLBACK_ENABLED', True)

    # -- Authentication --------------------------------------------------------

    @property
    def JWT_SECRET_KEY(self) -> str:
        return getattr(_dj, 'JWT_SECRET_KEY', _dj.SECRET_KEY)

    @property
    def JWT_ALGORITHM(self) -> str:
        return getattr(_dj, 'JWT_ALGORITHM', 'HS256')

    @property
    def AUTH_CACHE_TIMEOUT(self) -> int:
        return getattr(_dj, 'AUTH_CACHE_TIMEOUT', 300)

    @property
    def TENANT_USER_APP_LABEL(self) -> str:
        return getattr(_dj, 'TENANT_USER_APP_LABEL', 'auth')

    @property
    def TENANT_USER_MODEL_NAME(self) -> str:
        return getattr(_dj, 'TENANT_USER_MODEL_NAME', 'User')

    @property
    def REQUIRE_AUTH_BY_DEFAULT(self) -> bool:
        return getattr(_dj, 'REQUIRE_AUTH_BY_DEFAULT', True)

    @property
    def AUTH_EXEMPT_PATHS(self) -> list:
        return getattr(_dj, 'AUTH_EXEMPT_PATHS', [
            '/health/', '/metrics/', '/docs/', '/admin/',
            '/api/public/', '/schema/',
        ])

    @property
    def AUTH_OPTIONAL_PATHS(self) -> list:
        return getattr(_dj, 'AUTH_OPTIONAL_PATHS', [])

    # -- Public endpoints ------------------------------------------------------

    @property
    def PUBLIC_GET_ENDPOINTS(self) -> list:
        return getattr(_dj, 'PUBLIC_GET_ENDPOINTS', [])

    @property
    def CUSTOMER_SOURCE_REQUIRED_ENDPOINTS(self) -> list:
        return getattr(_dj, 'CUSTOMER_SOURCE_REQUIRED_ENDPOINTS', [])

    # -- Redis -----------------------------------------------------------------

    @property
    def REDIS_HOST(self) -> str:
        return getattr(_dj, 'REDIS_HOST', 'localhost')

    @property
    def REDIS_PORT(self) -> int:
        return getattr(_dj, 'REDIS_PORT', 6379)

    @property
    def REDIS_DB(self) -> int:
        return getattr(_dj, 'REDIS_DB', 0)


settings = _Settings()
