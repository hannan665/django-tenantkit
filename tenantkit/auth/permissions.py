"""
DRF Permission classes — token-based auth, super-admin, guest-or-auth.

NOTE: RBACPermission was removed because it depends on app-specific
User/Role/UserRole models. Consuming apps should implement their own
RBAC permission class using their own models.
"""

from rest_framework.permissions import BasePermission

from tenantkit.auth.jwt import auth_user
from tenantkit.exceptions import AuthenticationError, AuthServiceError


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        try:
            token = auth_user._extract_token(request)
            if not token:
                return False
            return auth_user.validate_token(token) is not None
        except (AuthenticationError, AuthServiceError):
            return False


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not getattr(request.user, 'is_authenticated', False):
            return False
        return getattr(request.user, 'is_superuser', False)


class GuestOrAuthenticatedPermission(BasePermission):
    """Allows all requests; object-level checks enforce ownership."""

    def has_permission(self, request, view):
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user and getattr(user, 'is_authenticated', False):
            if hasattr(obj, 'user_id'):
                return str(obj.user_id) == str(user.id)
            if hasattr(obj, 'user'):
                return obj.user == user
        return True
