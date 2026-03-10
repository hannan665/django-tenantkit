# Changelog

## [0.1.0] - 2024-03-10

### Added
- Initial release
- Schema-per-tenant backend (wraps django-tenants)
- Database-per-tenant backend with thread-safe connection registration
- `TenantMiddleware` — resolves tenant from `X-Tenant` header or host domain
- `AuthMiddleware` — JWT validation and tenant-scoped user lookup
- `BlockedUserMiddleware` — rejects blocked users
- `PublicEndpointsMiddleware` — marks public GET endpoints to skip auth
- `TenantDatabaseRouter` — routes queries to the correct schema/database
- `TenantMixin`, `DomainMixin` — model mixins wrapping django-tenants
- `TenantAuthentication`, `TenantUser` — DRF authentication integration
- `IsAuthenticated`, `IsSuperAdmin`, `GuestOrAuthenticatedPermission` — DRF permission classes
- Thread-safe context storage using `contextvars` (ASGI/async compatible)
- Centralized settings with sensible defaults
- Migration helpers for public and tenant schemas
