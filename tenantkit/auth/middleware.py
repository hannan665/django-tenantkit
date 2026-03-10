"""
Authentication-related middleware: AuthMiddleware, PublicEndpointsMiddleware, BlockedUserMiddleware.
"""

import logging

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from tenantkit.conf import settings as tk
from tenantkit.auth.jwt import auth_user
from tenantkit.exceptions import AuthenticationError
from tenantkit.tenancy.context import set_current_tenant

logger = logging.getLogger(__name__)


def _json_error(code, message, hint, status=400):
    return JsonResponse({
        'success': False, 'code': code,
        'error': {'message': message, 'hint': hint},
    }, status=status)


# -----------------------------------------------------------------------
# Auth Middleware
# -----------------------------------------------------------------------

class AuthMiddleware(MiddlewareMixin):
    """JWT authentication middleware — validates tokens, sets request.user_info."""

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.exempt_paths = tk.AUTH_EXEMPT_PATHS
        self.optional_paths = tk.AUTH_OPTIONAL_PATHS
        self.require_auth = tk.REQUIRE_AUTH_BY_DEFAULT
        self.require_tenant = tk.REQUIRE_TENANT_BY_DEFAULT

    def process_request(self, request):
        if getattr(request, 'is_public_request', False) or self._is_exempt(request):
            request.user_info = None
            return None

        tenant_resp = self._validate_tenant(request)
        if tenant_resp:
            return tenant_resp

        return self._authenticate(request, optional=self._is_optional(request))

    # -- tenant ----------------------------------------------------------

    def _validate_tenant(self, request):
        if getattr(request, 'tenant', None) or getattr(request, 'tenant_name', None):
            return None

        header = request.headers.get('X-Tenant', '').strip().lower()
        if header:
            request.tenant_name = header
            set_current_tenant(header)
            return None

        if self.require_tenant:
            return _json_error(
                'MISSING_TENANT_HEADER',
                'Missing X-Tenant header.',
                'All requests must include a valid X-Tenant header.',
            )
        return None

    # -- authentication --------------------------------------------------

    def _authenticate(self, request, optional=False):
        try:
            user_info = auth_user.get_user_info(request)
            if user_info is None and self.require_auth and not optional:
                return _json_error(
                    'AUTHENTICATION_REQUIRED',
                    'Authentication required.',
                    'Please provide a valid Authorization header with Bearer token.',
                    status=401,
                )
            self._set_user_context(request, user_info)
            return None
        except AuthenticationError as e:
            return self._auth_error_response(e)
        except Exception:
            return _json_error(
                'INTERNAL_ERROR',
                'Internal authentication error.',
                'Please try again or contact support.',
                status=500,
            )

    @staticmethod
    def _set_user_context(request, user_info):
        request.user_info = user_info
        if user_info:
            request.user_id = user_info.get('id')
            request.user_name = user_info.get('name') or user_info.get('username')
            request.user_email = user_info.get('email')
            request.user_roles = user_info.get('roles', [])
            request.user_permissions = user_info.get('permissions', [])
        else:
            request.user_id = None
            request.user_name = None
            request.user_email = None
            request.user_roles = []
            request.user_permissions = []

    def _auth_error_response(self, error):
        msg = str(error)
        mappings = {
            'User not found in tenant database': ('USER_NOT_FOUND', 'User not found in tenant database.'),
            'Token has expired': ('TOKEN_EXPIRED', 'Token has expired.'),
            'Invalid token signature': ('INVALID_SIGNATURE', 'Invalid token signature.'),
            'Invalid token': ('INVALID_TOKEN', 'Invalid authentication token.'),
            'Token validation failed': ('TOKEN_VALIDATION_ERROR', 'Token validation failed.'),
            'User is blocked': ('ACCOUNT_BLOCKED', 'Account Blocked'),
        }
        for key, (code, message) in mappings.items():
            if key in msg:
                return _json_error(code, message, msg, status=401)
        return _json_error('AUTHENTICATION_ERROR', 'Authentication failed.', msg, status=401)

    def _is_exempt(self, request):
        return any(request.path.startswith(p) for p in self.exempt_paths)

    def _is_optional(self, request):
        return any(request.path.startswith(p) for p in self.optional_paths)


# -----------------------------------------------------------------------
# Public Endpoints Middleware
# -----------------------------------------------------------------------

class PublicEndpointsMiddleware(MiddlewareMixin):
    """Marks public GET endpoints so auth middleware can skip them."""

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.public_get_endpoints = tk.PUBLIC_GET_ENDPOINTS
        self.customer_source_endpoints = tk.CUSTOMER_SOURCE_REQUIRED_ENDPOINTS
        self.require_tenant = tk.REQUIRE_TENANT_BY_DEFAULT
        self.header_name = tk.TENANT_HEADER_NAME

    def process_request(self, request):
        if not self._is_public_get(request):
            return None

        tenant_name = None
        if getattr(request, 'tenant', None):
            tenant_name = request.tenant.schema_name
        else:
            tenant_name = request.headers.get(self.header_name, '').strip().lower()
            if tenant_name:
                request.tenant_name = tenant_name
                set_current_tenant(tenant_name)

        if tenant_name:
            request.user_info = None
            request.is_public_request = True
            return None

        if self.require_tenant:
            return _json_error(
                'MISSING_TENANT_HEADER',
                f'Missing {self.header_name} header.',
                f'All requests must include a valid {self.header_name} header.',
            )
        return None

    def _is_public_get(self, request):
        if request.method.upper() != 'GET':
            return False
        path = request.path
        for ep in self.public_get_endpoints:
            if ep in self.customer_source_endpoints:
                if path.startswith(ep) and request.GET.get('source') == 'customer':
                    return True
            elif path.startswith(ep):
                return True
        return False


# -----------------------------------------------------------------------
# Blocked User Middleware
# -----------------------------------------------------------------------

class BlockedUserMiddleware:
    """Prevents blocked users from accessing the service."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_skip(request):
            return self.get_response(request)

        user_info = getattr(request, 'user_info', None)
        if user_info is None:
            return self.get_response(request)

        if isinstance(user_info, dict) and user_info.get('is_blocked', False):
            logger.warning("Blocked user %s attempted access to %s",
                           user_info.get('id', '?'), request.path)
            return JsonResponse({
                'detail': 'Your account has been blocked. Please contact support.',
                'code': 'USER_BLOCKED',
                'status': 'error',
            }, status=401)

        return self.get_response(request)

    @staticmethod
    def _should_skip(request):
        skip_paths = set(tk.AUTH_EXEMPT_PATHS) | set(tk.AUTH_OPTIONAL_PATHS)
        return any(request.path.startswith(p) for p in skip_paths)
