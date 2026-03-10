"""
DRF Authentication backend — maps request.user_info into a DRF-compatible user.
"""

from rest_framework import authentication


class TenantUser:
    """Lightweight user wrapper around the user_info dict set by AuthMiddleware."""

    def __init__(self, user_info: dict):
        self.user_info = user_info
        self.id = user_info.get('id')
        self.pk = self.id
        self.username = user_info.get('username') or user_info.get('email', '')
        self.email = user_info.get('email', '')
        self.first_name = user_info.get('first_name', '')
        self.last_name = user_info.get('last_name', '')
        self.roles = user_info.get('roles', [])
        self.permissions = user_info.get('permissions', [])
        self.is_authenticated = True
        self.is_anonymous = False
        self.is_active = True
        self.is_staff = 'admin' in self.roles
        self.is_superuser = 'superuser' in self.roles

    def get_full_name(self):
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username

    def get_short_name(self):
        return self.first_name or self.username

    def has_perm(self, perm, obj=None):
        return self.is_superuser or perm in self.permissions

    def has_perms(self, perm_list, obj=None):
        return self.is_superuser or all(p in self.permissions for p in perm_list)

    def has_module_perms(self, app_label):
        return self.is_superuser or any(
            p.startswith(f"{app_label}.") for p in self.permissions
        )

    def __str__(self):
        return self.username or f"User {self.id}"


class TenantAuthentication(authentication.BaseAuthentication):
    """DRF authentication class that picks up user_info set by AuthMiddleware."""

    def authenticate(self, request):
        user_info = getattr(request, 'user_info', None)
        if user_info is None:
            return None
        return (TenantUser(user_info), None)
