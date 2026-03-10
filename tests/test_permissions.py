"""Tests for tenantkit.auth.permissions — IsAuthenticated, IsSuperAdmin, GuestOrAuthenticated."""

import jwt
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import RequestFactory

from tenantkit.auth.authentication import TenantUser
from tenantkit.auth.permissions import (
    IsAuthenticated,
    IsSuperAdmin,
    GuestOrAuthenticatedPermission,
)
from tenantkit.tenancy.context import set_current_tenant, clear_context


def _make_token(user_id='1'):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {'user_id': user_id, 'iat': now, 'exp': now + timedelta(hours=1)},
        settings.SECRET_KEY,
        algorithm='HS256',
    )


class TestIsAuthenticated:

    def setup_method(self):
        set_current_tenant('test_tenant')
        self.perm = IsAuthenticated()

    def teardown_method(self):
        clear_context()

    @patch('tenantkit.auth.jwt.apps')
    @patch('tenantkit.auth.jwt.cache')
    def test_valid_token_allowed(self, mock_cache, mock_apps):
        cached = {'id': '1', 'email': 'test@acme.com'}
        mock_cache.get.return_value = cached

        token = _make_token()
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION=f'Bearer {token}')
        assert self.perm.has_permission(request, None) is True

    def test_no_token_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        assert self.perm.has_permission(request, None) is False

    def test_invalid_token_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/', HTTP_AUTHORIZATION='Bearer garbage')
        assert self.perm.has_permission(request, None) is False


class TestIsSuperAdmin:

    def setup_method(self):
        self.perm = IsSuperAdmin()

    def test_superuser_allowed(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = TenantUser({
            'id': '1', 'email': 'admin@acme.com', 'username': 'admin',
            'first_name': 'Admin', 'last_name': 'User',
            'roles': ['superuser'], 'permissions': [],
        })
        assert self.perm.has_permission(request, None) is True

    def test_regular_user_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = TenantUser({
            'id': '1', 'email': 'user@acme.com', 'username': 'user',
            'first_name': 'Regular', 'last_name': 'User',
            'roles': ['editor'], 'permissions': [],
        })
        assert self.perm.has_permission(request, None) is False

    def test_no_user_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = None
        assert self.perm.has_permission(request, None) is False

    def test_anonymous_user_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        user = MagicMock()
        user.is_authenticated = False
        request.user = user
        assert self.perm.has_permission(request, None) is False


class TestGuestOrAuthenticatedPermission:

    def setup_method(self):
        self.perm = GuestOrAuthenticatedPermission()

    def test_has_permission_always_true(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        assert self.perm.has_permission(request, None) is True

    def test_object_owner_allowed(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = TenantUser({
            'id': '42', 'email': 'owner@acme.com', 'username': 'owner',
            'first_name': '', 'last_name': '',
            'roles': [], 'permissions': [],
        })

        obj = MagicMock()
        obj.user_id = '42'
        assert self.perm.has_object_permission(request, None, obj) is True

    def test_non_owner_denied(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = TenantUser({
            'id': '42', 'email': 'other@acme.com', 'username': 'other',
            'first_name': '', 'last_name': '',
            'roles': [], 'permissions': [],
        })

        obj = MagicMock()
        obj.user_id = '99'
        del obj.user  # ensure only user_id is checked
        assert self.perm.has_object_permission(request, None, obj) is False

    def test_guest_allowed(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user = None

        obj = MagicMock()
        obj.user_id = '42'
        assert self.perm.has_object_permission(request, None, obj) is True
