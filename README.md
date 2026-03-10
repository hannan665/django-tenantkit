# django-tenantkit

Pluggable multi-tenant toolkit for Django. Wraps [django-tenants](https://github.com/django-tenants/django-tenants) and adds tenant-scoped JWT authentication, flexible tenant resolution, and a full middleware stack. Supports both **schema-per-tenant** and **database-per-tenant** modes.

## Features

- **Dual-mode tenancy** — `schema` (PostgreSQL schemas via django-tenants) or `database` (separate DB per tenant), switched by a single setting
- **Tenant resolution** — `X-Tenant` header (domain or schema name) with host domain fallback
- **JWT authentication** — local token decoding, tenant-scoped user lookup, result caching
- **Middleware stack** — `TenantMiddleware` → `AuthMiddleware` → `BlockedUserMiddleware`
- **DRF integration** — `TenantAuthentication`, `TenantUser`, permission classes
- **ASGI compatible** — context storage uses `contextvars`, safe under async Django
- **Database router** — `TenantDatabaseRouter` for query routing across schemas/databases
- **Migration helpers** — run public or tenant migrations in either mode

## Installation

```bash
pip install django-tenantkit
```

## Quick Start

### 1. Create Tenant and Domain models

```python
# tenancy/models.py
from django.db import models
from tenantkit.tenancy.models import TenantMixin, DomainMixin

class Tenant(TenantMixin):
    name = models.CharField(max_length=100)
    auto_create_schema = True

class Domain(DomainMixin):
    pass
```

### 2. Configure settings

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': 'your_db',
        'USER': 'postgres',
        'PASSWORD': 'postgres',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

INSTALLED_APPS = [
    'django_tenants',
    'tenancy',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'rest_framework',
    'tenantkit',
    # ... your apps
]

TENANT_DB_MODE = 'schema'          # or 'database'
TENANT_MODEL = 'tenancy.Tenant'
TENANT_DOMAIN_MODEL = 'tenancy.Domain'

TENANT_APPS = ['django.contrib.auth', ...]    # apps in tenant schemas
SHARED_APPS = ['django_tenants', 'tenancy', ...]  # apps in public schema

DATABASE_ROUTERS = [
    'django_tenants.routers.TenantSyncRouter',
    'tenantkit.tenancy.TenantDatabaseRouter',
]
```

### 3. Add middleware

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'tenantkit.tenancy.middleware.TenantMiddleware',
    'tenantkit.auth.middleware.AuthMiddleware',
    'tenantkit.auth.middleware.BlockedUserMiddleware',
    # ... rest of middleware
]
```

### 4. DRF authentication (optional)

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'tenantkit.auth.TenantAuthentication',
    ],
}
```

### 5. Run migrations and create a tenant

```bash
python manage.py migrate_schemas --shared
```

```python
from tenancy.models import Tenant, Domain

public = Tenant(schema_name='public', name='Public')
public.save()
Domain.objects.create(domain='localhost', tenant=public, is_primary=True)

tenant = Tenant(schema_name='acme', name='Acme Corp')
tenant.save()  # auto-creates schema and runs migrations
Domain.objects.create(domain='acme.localhost', tenant=tenant, is_primary=True)
```

## Usage

### Request attributes set by AuthMiddleware

```python
request.user_info    # {'id': '1', 'email': '...', 'roles': [...], ...}
request.user_id      # '1'
request.user_email   # 'test@acme.com'
request.user_roles   # ['admin']

# DRF (via TenantAuthentication)
request.user.has_perm('orders.view_order')
request.user.is_superuser  # True if 'superuser' in roles
```

### Permissions

```python
from tenantkit.auth.permissions import IsAuthenticated, IsSuperAdmin

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def protected_view(request): ...

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def admin_view(request): ...
```

### Path exemptions

```python
TENANT_EXEMPT_PATHS = ['/health/', '/admin/', '/docs/']
AUTH_EXEMPT_PATHS   = ['/health/', '/admin/', '/docs/']
AUTH_OPTIONAL_PATHS = ['/api/catalog/']   # tenant required, auth optional
PUBLIC_GET_ENDPOINTS = ['/api/menu/']     # GET only, no auth, tenant required
```

### Generating tokens (for testing)

```python
import jwt
payload = {'user_id': str(user.id), 'exp': ...}
token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')
```

### Making requests

```bash
curl -H "X-Tenant: acme" \
     -H "Authorization: Bearer eyJ..." \
     http://localhost:8000/api/me/
```

## Settings Reference

### Tenancy

| Setting | Default | Description |
|---|---|---|
| `TENANT_DB_MODE` | `'schema'` | `'schema'` or `'database'` |
| `TENANT_MODEL` | `'tenancy.Tenant'` | Your Tenant model |
| `TENANT_DOMAIN_MODEL` | `'tenancy.Domain'` | Your Domain model |
| `TENANT_HEADER_NAME` | `'X-Tenant'` | HTTP header for tenant resolution |
| `REQUIRE_TENANT_BY_DEFAULT` | `True` | Reject requests without tenant context |
| `TENANT_EXEMPT_PATHS` | `['/health/', ...]` | Paths that bypass tenant resolution |
| `TENANT_APPS` | `[]` | App labels routed to tenant schemas/databases |
| `SHARED_APPS` | `[]` | App labels routed to public schema / default database |
| `TENANT_DB_NAME_PREFIX` | `'tenant_'` | Prefix for database names (database mode) |
| `TENANT_DB_TEMPLATE` | `{}` | Extra DB config merged with `default` for tenant databases |

### Authentication

| Setting | Default | Description |
|---|---|---|
| `JWT_SECRET_KEY` | `SECRET_KEY` | Key used to verify JWT signatures |
| `JWT_ALGORITHM` | `'HS256'` | JWT signing algorithm |
| `AUTH_CACHE_TIMEOUT` | `300` | Seconds to cache user data (capped to token lifetime) |
| `TENANT_USER_APP_LABEL` | `'auth'` | App label of your User model |
| `TENANT_USER_MODEL_NAME` | `'User'` | Model name of your User model |
| `REQUIRE_AUTH_BY_DEFAULT` | `True` | Reject unauthenticated requests |
| `AUTH_EXEMPT_PATHS` | `['/health/', ...]` | Paths that bypass authentication |
| `AUTH_OPTIONAL_PATHS` | `[]` | Paths where auth is optional |

## Error Responses

All errors return JSON:

```json
{"success": false, "code": "ERROR_CODE", "error": {"message": "...", "hint": "..."}}
```

| Code | Status | When |
|---|---|---|
| `MISSING_TENANT_HEADER` | 400 | No `X-Tenant` and `REQUIRE_TENANT_BY_DEFAULT=True` |
| `INVALID_TENANT` | 404 | `X-Tenant` value not found |
| `AUTHENTICATION_REQUIRED` | 401 | No Bearer token |
| `TOKEN_EXPIRED` | 401 | JWT `exp` in the past |
| `INVALID_SIGNATURE` | 401 | Wrong signing secret |
| `USER_NOT_FOUND` | 401 | `user_id` not in tenant DB |
| `ACCOUNT_BLOCKED` | 401 | `is_blocked=True` |

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Requirements

- Python >= 3.9
- Django >= 4.2
- django-tenants >= 3.8
- Django REST Framework >= 3.14
- PyJWT >= 2.0
- PostgreSQL

## License

MIT
