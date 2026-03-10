"""
Authentication module — JWT validation, DRF backend, permissions.
"""

from .jwt import AuthUser, get_auth_user, auth_user
from .authentication import TenantAuthentication, TenantUser
from .permissions import IsAuthenticated, IsSuperAdmin, GuestOrAuthenticatedPermission
from .middleware import AuthMiddleware, BlockedUserMiddleware, PublicEndpointsMiddleware

__all__ = [
    'AuthUser',
    'get_auth_user',
    'auth_user',
    'TenantAuthentication',
    'TenantUser',
    'IsAuthenticated',
    'IsSuperAdmin',
    'GuestOrAuthenticatedPermission',
    'AuthMiddleware',
    'BlockedUserMiddleware',
    'PublicEndpointsMiddleware',
]
