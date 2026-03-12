"""Tests for tenantkit.auth.jwt — JWT validation and user lookup."""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import RequestFactory

from tenantkit.auth.jwt import AuthUser
from tenantkit.exceptions import AuthenticationError, UserBlockedError
from tenantkit.tenancy.context import set_current_tenant, clear_context


def _make_token(payload=None, secret=None, algorithm='HS256'):
    """Helper to generate a JWT token."""
    secret = secret or settings.SECRET_KEY
    base = {
        'user_id': '1',
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=1),
    }
    if payload:
        base.update(payload)
    return jwt.encode(base, secret, algorithm=algorithm)


def _make_request(token=None, tenant_header=None):
    """Helper to create a Django request with optional auth header."""
    factory = RequestFactory()
    headers = {}
    if token:
        headers['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    if tenant_header:
        headers['HTTP_X_TENANT'] = tenant_header
    return factory.get('/api/test/', **headers)


def _mock_user(user_id='1', email='test@acme.com', is_active=True,
               is_blocked=False, is_staff=False, is_superuser=False):
    """Create a mock User object."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.username = email
    user.first_name = 'Test'
    user.last_name = 'User'
    user.full_name = 'Test User'
    user.is_active = is_active
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    user.date_joined = datetime.now(timezone.utc)
    user.last_login = None
    user.is_blocked = is_blocked
    # No roles/permissions by default
    del user.roles
    del user.driver_id
    del user.is_login_active
    user.user_permissions = MagicMock()
    user.user_permissions.all.return_value = []
    return user


class TestTokenExtraction:

    def setup_method(self):
        self.auth = AuthUser()

    def test_extract_bearer_token(self):
        request = _make_request(token='mytoken123')
        assert self.auth._extract_token(request) == 'mytoken123'

    def test_extract_no_header(self):
        request = _make_request()
        assert self.auth._extract_token(request) is None

    def test_extract_non_bearer_header(self):
        factory = RequestFactory()
        request = factory.get('/test/', HTTP_AUTHORIZATION='Basic abc123')
        assert self.auth._extract_token(request) is None

    def test_extract_empty_bearer(self):
        factory = RequestFactory()
        request = factory.get('/test/', HTTP_AUTHORIZATION='Bearer ')
        token = self.auth._extract_token(request)
        assert token == ''


class TestTokenDecoding:

    def setup_method(self):
        self.auth = AuthUser()

    def test_decode_valid_token(self):
        token = _make_token({'user_id': '42'})
        payload = self.auth._decode(token)
        assert payload['user_id'] == '42'

    def test_decode_expired_token(self):
        token = _make_token({
            'exp': datetime.now(timezone.utc) - timedelta(hours=1),
        })
        with pytest.raises(AuthenticationError, match='Token has expired'):
            self.auth._decode(token)

    def test_decode_invalid_signature(self):
        token = jwt.encode(
            {'user_id': '1', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)},
            'wrong-secret',
            algorithm='HS256',
        )
        with pytest.raises(AuthenticationError, match='Invalid token signature'):
            self.auth._decode(token)

    def test_decode_malformed_token(self):
        with pytest.raises(AuthenticationError, match='Invalid token'):
            self.auth._decode('not.a.valid.jwt')

    def test_decode_empty_token(self):
        with pytest.raises(AuthenticationError, match='Invalid token'):
            self.auth._decode('')


class TestExpiryCheck:

    def setup_method(self):
        self.auth = AuthUser()

    def test_valid_expiry(self):
        payload = {'exp': (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()}
        self.auth._check_expiry(payload)  # should not raise

    def test_expired(self):
        payload = {'exp': (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()}
        with pytest.raises(AuthenticationError, match='Token has expired'):
            self.auth._check_expiry(payload)

    def test_no_expiry_field(self):
        self.auth._check_expiry({})  # should not raise — no exp means no check


class TestValidateToken:

    def setup_method(self):
        self.auth = AuthUser()
        set_current_tenant('test_tenant')

    def teardown_method(self):
        clear_context()

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_valid_token_returns_user_data(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        user = _mock_user(user_id='1')
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        token = _make_token({'user_id': '1'})
        result = self.auth.validate_token(token)

        assert result['id'] == '1'
        assert result['email'] == 'test@acme.com'
        assert result['tenant'] == 'test_tenant'

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_cached_result_returned(self, mock_cache, mock_apps):
        cached_data = {'id': '1', 'email': 'cached@test.com'}
        mock_cache.get.return_value = cached_data

        token = _make_token({'user_id': '1'})
        result = self.auth.validate_token(token)

        assert result == cached_data
        mock_apps.get_model.assert_not_called()

    def test_no_token_raises(self):
        with pytest.raises(AuthenticationError, match='No token provided'):
            self.auth.validate_token('')

    def test_no_tenant_context_raises(self):
        clear_context()
        token = _make_token({'user_id': '1'})
        with pytest.raises(AuthenticationError, match='No tenant context'):
            self.auth.validate_token(token)

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_not_found_raises(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = None
        mock_apps.get_model.return_value = mock_model

        token = _make_token({'user_id': '999'})
        with pytest.raises(AuthenticationError, match='User not found'):
            self.auth.validate_token(token)

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_blocked_user_raises(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        user = _mock_user(user_id='1', is_blocked=True)
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        token = _make_token({'user_id': '1'})
        with pytest.raises(AuthenticationError, match='User is blocked'):
            self.auth.validate_token(token)

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_token_with_sub_claim(self, mock_cache, mock_apps):
        """Tokens using 'sub' instead of 'user_id' should work."""
        mock_cache.get.return_value = None
        user = _mock_user(user_id='5')
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        token = _make_token({'sub': '5'})
        # Remove user_id from payload — only 'sub' present
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        payload.pop('user_id', None)
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

        result = self.auth.validate_token(token)
        assert result['id'] == '5'


class TestTenantClaimCheck:

    def setup_method(self):
        self.auth = AuthUser()

    def test_matching_tenant_claim_passes(self):
        payload = {'tenant': 'acme', 'user_id': '1'}
        self.auth._check_tenant_claim(payload, 'acme')  # should not raise

    def test_mismatched_tenant_claim_raises(self):
        payload = {'tenant': 'tenant_b', 'user_id': '1'}
        with pytest.raises(AuthenticationError, match='Token does not belong to this tenant'):
            self.auth._check_tenant_claim(payload, 'tenant_a')

    def test_no_tenant_claim_passes(self):
        """Tokens without a tenant claim are allowed (backward compatible)."""
        payload = {'user_id': '1'}
        self.auth._check_tenant_claim(payload, 'acme')  # should not raise

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_cross_tenant_token_rejected(self, mock_cache, mock_apps):
        """Token issued for tenant_b must be rejected when active tenant is tenant_a."""
        mock_cache.get.return_value = None
        set_current_tenant('tenant_a')

        token = _make_token({'user_id': '1', 'tenant': 'tenant_b'})
        with pytest.raises(AuthenticationError, match='Token does not belong to this tenant'):
            self.auth.validate_token(token)

        clear_context()

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_correct_tenant_token_accepted(self, mock_cache, mock_apps):
        """Token with matching tenant claim authenticates normally."""
        mock_cache.get.return_value = None
        user = _mock_user(user_id='1')
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        set_current_tenant('acme')
        token = _make_token({'user_id': '1', 'tenant': 'acme'})
        result = self.auth.validate_token(token)
        assert result['tenant'] == 'acme'

        clear_context()


class TestGetUserInfo:

    def setup_method(self):
        self.auth = AuthUser()
        set_current_tenant('test_tenant')

    def teardown_method(self):
        clear_context()

    def test_no_auth_header_returns_none(self):
        request = _make_request()
        result = self.auth.get_user_info(request)
        assert result is None

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_valid_auth_header_returns_user(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        user = _mock_user()
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = user
        mock_apps.get_model.return_value = mock_model

        token = _make_token()
        request = _make_request(token=token)
        result = self.auth.get_user_info(request)
        assert result is not None
        assert result['id'] == '1'


class TestHasRole:

    def setup_method(self):
        self.auth = AuthUser()
        set_current_tenant('test_tenant')

    def teardown_method(self):
        clear_context()

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_has_matching_role(self, mock_cache, mock_apps):
        cached = {'id': '1', 'roles': ['admin', 'editor']}
        mock_cache.get.return_value = cached

        token = _make_token()
        assert self.auth.has_role(token, ['admin']) is True
        assert self.auth.has_role(token, 'editor') is True

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_missing_role(self, mock_cache, mock_apps):
        cached = {'id': '1', 'roles': ['viewer']}
        mock_cache.get.return_value = cached

        token = _make_token()
        assert self.auth.has_role(token, ['admin']) is False

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_invalid_token_returns_false(self, mock_cache, mock_apps):
        mock_cache.get.return_value = None
        assert self.auth.has_role('garbage', ['admin']) is False


class TestHasPermission:

    def setup_method(self):
        self.auth = AuthUser()
        set_current_tenant('test_tenant')

    def teardown_method(self):
        clear_context()

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_has_permission(self, mock_cache, mock_apps):
        cached = {'id': '1', 'permissions': ['orders.view_order', 'orders.add_order']}
        mock_cache.get.return_value = cached

        token = _make_token()
        assert self.auth.has_permission(token, 'orders.view_order') is True

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_user_missing_permission(self, mock_cache, mock_apps):
        cached = {'id': '1', 'permissions': ['orders.view_order']}
        mock_cache.get.return_value = cached

        token = _make_token()
        assert self.auth.has_permission(token, 'orders.delete_order') is False


class TestSerializeUser:

    def test_basic_fields(self):
        user = _mock_user(user_id='42', email='jane@acme.com')
        data = AuthUser._serialize_user(user)
        assert data['id'] == '42'
        assert data['email'] == 'jane@acme.com'
        assert data['first_name'] == 'Test'
        assert data['is_active'] is True

    def test_blocked_field_included(self):
        user = _mock_user(is_blocked=True)
        data = AuthUser._serialize_user(user)
        assert data['is_blocked'] is True

    def test_tenant_included_when_provided(self):
        user = _mock_user()
        data = AuthUser._serialize_user(user, tenant_name='acme')
        assert data['tenant'] == 'acme'

    def test_roles_from_queryset(self):
        user = _mock_user()
        role1 = MagicMock()
        role1.name = 'admin'
        role2 = MagicMock()
        role2.name = 'editor'
        user.roles = MagicMock()
        user.roles.all.return_value = [role1, role2]
        data = AuthUser._serialize_user(user)
        assert data['roles'] == ['admin', 'editor']

    def test_roles_from_list(self):
        user = _mock_user()
        user.roles = ['admin', 'viewer']
        data = AuthUser._serialize_user(user)
        assert data['roles'] == ['admin', 'viewer']
