"""
JWT token validation and tenant-scoped user lookup.
"""

import jwt
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from django.apps import apps
from django.core.cache import cache
from django.http import HttpRequest

from tenantkit.conf import settings as tk
from tenantkit.exceptions import AuthenticationError, AuthServiceError, UserBlockedError
from tenantkit.tenancy.context import get_current_tenant

logger = logging.getLogger(__name__)


class AuthUser:

    def __init__(self):
        self.cache_timeout = tk.AUTH_CACHE_TIMEOUT
        self.jwt_secret_key = tk.JWT_SECRET_KEY
        self.jwt_algorithm = tk.JWT_ALGORITHM
        self.user_app_label = tk.TENANT_USER_APP_LABEL
        self.user_model_name = tk.TENANT_USER_MODEL_NAME

    # -- public API ------------------------------------------------------

    def validate_token(self, token: str, tenant_name: Optional[str] = None) -> Optional[Dict]:
        if not token:
            raise AuthenticationError("No token provided")

        tenant_name = self._resolve_tenant(tenant_name)

        cache_key = f"tk_auth_{tenant_name}_{hash(token)}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        user_data = self._validate_and_process(token, tenant_name)
        ttl = self._compute_cache_ttl(token)
        cache.set(cache_key, user_data, ttl)
        return user_data

    def get_user_info(self, request: HttpRequest) -> Optional[Dict]:
        token = self._extract_token(request)
        if not token:
            return None
        return self.validate_token(token)

    def get_user_by_id(self, user_id: str, tenant_name: Optional[str] = None) -> Optional[Dict]:
        if not user_id:
            return None
        tenant_name = tenant_name or get_current_tenant()
        if not tenant_name:
            return None

        cache_key = f"tk_user_{tenant_name}_{user_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            User = apps.get_model(self.user_app_label, self.user_model_name)
            user = User.objects.filter(id=user_id, is_active=True).first()
            if not user:
                return None
            data = self._serialize_user(user, tenant_name)
            cache.set(cache_key, data, self.cache_timeout)
            return data
        except Exception as e:
            logger.error("Failed to fetch user by ID: %s", e, exc_info=True)
            return None

    def has_role(self, token: str, allowed_roles: Union[str, List[str]]) -> bool:
        try:
            data = self.validate_token(token)
            if not data:
                return False
            user_roles = data.get('roles', [])
            if isinstance(user_roles, str):
                user_roles = [user_roles]
            if isinstance(allowed_roles, str):
                allowed_roles = [allowed_roles]
            return any(r in user_roles for r in allowed_roles)
        except (AuthenticationError, AuthServiceError):
            return False

    def has_permission(self, token: str, permission: str) -> bool:
        try:
            data = self.validate_token(token)
            return permission in (data or {}).get('permissions', [])
        except (AuthenticationError, AuthServiceError):
            return False

    # -- internal --------------------------------------------------------

    def _resolve_tenant(self, tenant_name: Optional[str]) -> str:
        if not tenant_name:
            tenant_name = get_current_tenant()
        if not tenant_name:
            raise AuthenticationError("No tenant context available for authentication")
        return tenant_name

    def _extract_token(self, request: HttpRequest) -> Optional[str]:
        header = request.META.get('HTTP_AUTHORIZATION', '')
        if header.startswith('Bearer '):
            return header.split(' ', 1)[1]
        return None

    def _validate_and_process(self, token: str, tenant_name: str) -> Dict:
        try:
            payload = self._decode(token)
            self._check_expiry(payload)
            user_id = payload.get('user_id') or payload.get('sub')
            if not user_id:
                raise AuthenticationError("No user_id found in token")
            return self._build_user_data(user_id, payload, tenant_name)
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
        except UserBlockedError:
            raise AuthenticationError("User is blocked")
        except AuthenticationError:
            raise
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {e}")

    def _decode(self, token: str) -> Dict:
        try:
            return jwt.decode(token, self.jwt_secret_key, algorithms=[self.jwt_algorithm])
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token has expired")
        except jwt.InvalidSignatureError:
            raise AuthenticationError("Invalid token signature")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")

    @staticmethod
    def _check_expiry(payload: Dict):
        exp = payload.get('exp')
        if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
            raise AuthenticationError("Token has expired")

    def _compute_cache_ttl(self, token: str) -> int:
        """Cap cache timeout to the token's remaining lifetime."""
        try:
            payload = jwt.decode(
                token, self.jwt_secret_key, algorithms=[self.jwt_algorithm]
            )
            exp = payload.get('exp')
            if exp:
                remaining = exp - datetime.now(timezone.utc).timestamp()
                return min(self.cache_timeout, max(0, int(remaining)))
        except Exception:
            pass
        return self.cache_timeout

    def _build_user_data(self, user_id: str, payload: Dict, tenant_name: str) -> Dict:
        data = self._get_user_from_db(user_id)
        if not data:
            raise AuthenticationError("User not found in tenant database")
        if data.get('is_blocked'):
            raise UserBlockedError("User is blocked")
        data.update({'token_claims': payload, 'tenant': tenant_name})
        return data

    def _get_user_from_db(self, user_id: str) -> Optional[Dict]:
        try:
            User = apps.get_model(self.user_app_label, self.user_model_name)
            user = User.objects.filter(id=user_id, is_active=True).first()
            if not user:
                return None
            return self._serialize_user(user)
        except Exception as e:
            logger.error("Failed to fetch user from tenant DB: %s", e, exc_info=True)
            return None

    @staticmethod
    def _serialize_user(user, tenant_name: Optional[str] = None) -> Dict:
        data = {
            'id': str(user.id),
            'email': user.email,
            'username': user.email,
            'first_name': getattr(user, 'first_name', ''),
            'last_name': getattr(user, 'last_name', ''),
            'full_name': getattr(user, 'full_name', ''),
            'is_active': getattr(user, 'is_active', True),
            'is_staff': getattr(user, 'is_staff', False),
            'is_superuser': getattr(user, 'is_superuser', False),
            'date_joined': getattr(user, 'date_joined', None),
            'last_login': getattr(user, 'last_login', None),
        }
        if tenant_name:
            data['tenant'] = tenant_name
        if hasattr(user, 'is_blocked'):
            data['is_blocked'] = user.is_blocked
        if hasattr(user, 'driver_id'):
            data['driver_id'] = getattr(user, 'driver_id', None)
        if hasattr(user, 'is_login_active'):
            data['is_login_active'] = getattr(user, 'is_login_active', None)

        # Roles
        if hasattr(user, 'roles'):
            roles = user.roles
            data['roles'] = [r.name for r in roles.all()] if hasattr(roles, 'all') else roles
        else:
            data['roles'] = []

        # Permissions
        if hasattr(user, 'user_permissions'):
            perms = user.user_permissions
            if hasattr(perms, 'all'):
                data['permissions'] = [
                    f"{p.content_type.app_label}.{p.codename}" for p in perms.all()
                ]
            else:
                data['permissions'] = perms
        else:
            data['permissions'] = []

        return data


# -- singleton & proxy ---------------------------------------------------

_instance: Optional[AuthUser] = None


def get_auth_user() -> AuthUser:
    global _instance
    if _instance is None:
        _instance = AuthUser()
    return _instance


class _AuthUserProxy:
    def __getattr__(self, name):
        return getattr(get_auth_user(), name)

    def __call__(self, *args, **kwargs):
        return get_auth_user()


auth_user = _AuthUserProxy()
