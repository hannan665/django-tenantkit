"""Tests for tenantkit middleware — TenantMiddleware, AuthMiddleware, BlockedUserMiddleware."""

import json
import jwt
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import RequestFactory

from tenantkit.tenancy.context import clear_context, get_current_tenant
from tenantkit.tenancy.middleware import TenantMiddleware
from tenantkit.auth.middleware import AuthMiddleware, BlockedUserMiddleware


def _ok_response(request):
    from django.http import JsonResponse
    return JsonResponse({'ok': True})


def _make_token(user_id='1', expired=False, secret=None):
    secret = secret or settings.SECRET_KEY
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)
    return jwt.encode({'user_id': user_id, 'iat': now, 'exp': exp}, secret, algorithm='HS256')


# ═══════════════════════════════════════════════════════════════════════
# TenantMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestTenantMiddleware:

    def setup_method(self):
        clear_context()
        self.middleware = TenantMiddleware(_ok_response)

    def teardown_method(self):
        clear_context()

    def test_exempt_path_skips_tenant_resolution(self):
        factory = RequestFactory()
        request = factory.get('/health/')
        response = self.middleware(request)
        assert response.status_code == 200

    @patch('tenantkit.tenancy.middleware.get_backend')
    def test_valid_x_tenant_header(self, mock_backend):
        backend_instance = MagicMock()
        mock_backend.return_value = backend_instance

        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        # Mock resolver to return a tenant
        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(None, 'tenant_acme', 'x-tenant-schema')):
            response = self.middleware(request)

        assert response.status_code == 200
        assert request.tenant_name == 'tenant_acme'
        assert request.tenant_resolution_method == 'x-tenant-schema'
        backend_instance.activate.assert_called_once_with('tenant_acme')

    def test_missing_tenant_header_rejected(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(None, None, None)):
            response = self.middleware(request)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert data['code'] == 'MISSING_TENANT_HEADER'

    def test_invalid_tenant_returns_404(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='nonexistent')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(None, 'nonexistent', 'failed')):
            response = self.middleware(request)

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data['code'] == 'INVALID_TENANT'

    @patch('tenantkit.tenancy.middleware.get_backend')
    def test_backend_activate_failure_returns_500(self, mock_backend):
        backend_instance = MagicMock()
        backend_instance.activate.side_effect = Exception('connection failed')
        mock_backend.return_value = backend_instance

        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(MagicMock(), 'tenant_acme', 'x-tenant-schema')):
            response = self.middleware(request)

        assert response.status_code == 500
        assert json.loads(response.content)['code'] == 'TENANT_SWITCH_ERROR'


# ═══════════════════════════════════════════════════════════════════════
# AuthMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestAuthMiddleware:

    def setup_method(self):
        clear_context()
        self.middleware = AuthMiddleware(_ok_response)

    def teardown_method(self):
        clear_context()

    def test_exempt_path_skips_auth(self):
        factory = RequestFactory()
        request = factory.get('/health/')
        response = self.middleware.process_request(request)
        assert response is None  # passes through
        assert request.user_info is None

    def test_missing_tenant_rejected(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        response = self.middleware.process_request(request)
        assert response.status_code == 400
        assert json.loads(response.content)['code'] == 'MISSING_TENANT_HEADER'

    def test_missing_auth_token_rejected(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.tenant_name = 'test_tenant'
        response = self.middleware.process_request(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] == 'AUTHENTICATION_REQUIRED'

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_valid_token_sets_user_info(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        user = MagicMock()
        user.id = '1'
        user.email = 'test@acme.com'
        user.username = 'test@acme.com'
        user.first_name = 'Test'
        user.last_name = 'User'
        user.full_name = 'Test User'
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.date_joined = datetime.now(timezone.utc)
        user.last_login = None
        del user.is_blocked
        del user.roles
        del user.driver_id
        del user.is_login_active
        user.user_permissions = MagicMock()
        user.user_permissions.all.return_value = []
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        from tenantkit.tenancy.context import set_current_tenant
        set_current_tenant('test_tenant')

        token = _make_token()
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION=f'Bearer {token}')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response is None  # passes through
        assert request.user_info is not None
        assert request.user_id == '1'

    def test_expired_token_rejected(self):
        from tenantkit.tenancy.context import set_current_tenant
        set_current_tenant('test_tenant')

        token = _make_token(expired=True)
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION=f'Bearer {token}')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] == 'TOKEN_EXPIRED'

    def test_invalid_token_rejected(self):
        from tenantkit.tenancy.context import set_current_tenant
        set_current_tenant('test_tenant')

        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION='Bearer garbage.token')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] in ('INVALID_TOKEN', 'INVALID_SIGNATURE',
                                             'TOKEN_VALIDATION_ERROR')

    def test_wrong_secret_rejected(self):
        from tenantkit.tenancy.context import set_current_tenant
        set_current_tenant('test_tenant')

        token = _make_token(secret='wrong-secret-key')
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION=f'Bearer {token}')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] == 'INVALID_SIGNATURE'

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_not_found_rejected(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = None
        mock_apps.get_model.return_value = mock_model

        from tenantkit.tenancy.context import set_current_tenant
        set_current_tenant('test_tenant')

        token = _make_token(user_id='999')
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION=f'Bearer {token}')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] == 'USER_NOT_FOUND'

    def test_optional_path_allows_no_token(self):
        factory = RequestFactory()
        request = factory.get('/api/optional/test/')
        request.tenant_name = 'test_tenant'

        response = self.middleware.process_request(request)
        assert response is None  # passes through
        assert request.user_info is None

    def test_public_request_flag_skips_auth(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.is_public_request = True

        response = self.middleware.process_request(request)
        assert response is None
        assert request.user_info is None


# ═══════════════════════════════════════════════════════════════════════
# TenantMiddleware — context cleanup & error sanitization
# ═══════════════════════════════════════════════════════════════════════

class TestTenantMiddlewareContextCleanup:

    def setup_method(self):
        clear_context()
        self.middleware = TenantMiddleware(_ok_response)

    def teardown_method(self):
        clear_context()

    @patch('tenantkit.tenancy.middleware.get_backend')
    def test_context_cleared_after_successful_request(self, mock_backend):
        backend_instance = MagicMock()
        mock_backend.return_value = backend_instance

        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(None, 'tenant_acme', 'x-tenant-schema')):
            self.middleware(request)

        # Context must be cleared after request
        from tenantkit.tenancy.context import get_current_tenant
        assert get_current_tenant() is None
        backend_instance.deactivate.assert_called_once()

    @patch('tenantkit.tenancy.middleware.get_backend')
    def test_context_cleared_after_backend_exception(self, mock_backend):
        backend_instance = MagicMock()
        backend_instance.activate.side_effect = RuntimeError('crash')
        mock_backend.return_value = backend_instance

        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='tenant_acme')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(MagicMock(), 'tenant_acme', 'x-tenant-schema')):
            response = self.middleware(request)

        assert response.status_code == 500
        from tenantkit.tenancy.context import get_current_tenant
        assert get_current_tenant() is None

    def test_invalid_tenant_error_does_not_leak_name(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_X_TENANT='secret-tenant')

        with patch.object(self.middleware._resolver, 'resolve',
                         return_value=(None, 'secret-tenant', 'failed')):
            response = self.middleware(request)

        import json
        data = json.loads(response.content)
        assert response.status_code == 404
        assert 'secret-tenant' not in data['error']['message']


# ═══════════════════════════════════════════════════════════════════════
# BlockedUserMiddleware
# ═══════════════════════════════════════════════════════════════════════

class TestBlockedUserMiddleware:

    def setup_method(self):
        self.middleware = BlockedUserMiddleware(_ok_response)

    def test_no_user_info_passes_through(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user_info = None
        response = self.middleware(request)
        assert response.status_code == 200

    def test_active_user_passes_through(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user_info = {'id': '1', 'is_blocked': False}
        response = self.middleware(request)
        assert response.status_code == 200

    def test_blocked_user_rejected(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user_info = {'id': '1', 'is_blocked': True}
        response = self.middleware(request)
        assert response.status_code == 401
        assert json.loads(response.content)['code'] == 'USER_BLOCKED'

    def test_exempt_path_not_blocked(self):
        factory = RequestFactory()
        request = factory.get('/health/')
        request.user_info = {'id': '1', 'is_blocked': True}
        response = self.middleware(request)
        assert response.status_code == 200
