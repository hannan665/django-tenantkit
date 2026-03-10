"""Tests for tenantkit.auth.authentication — DRF TenantAuthentication + TenantUser."""

import pytest
from unittest.mock import MagicMock

from django.test import RequestFactory

from tenantkit.auth.authentication import TenantAuthentication, TenantUser


class TestTenantUser:

    def _make_user_info(self, **overrides):
        base = {
            'id': '1',
            'email': 'test@acme.com',
            'username': 'test@acme.com',
            'first_name': 'Test',
            'last_name': 'User',
            'roles': [],
            'permissions': [],
        }
        base.update(overrides)
        return base

    def test_basic_attributes(self):
        user = TenantUser(self._make_user_info())
        assert user.id == '1'
        assert user.email == 'test@acme.com'
        assert user.is_authenticated is True
        assert user.is_anonymous is False

    def test_admin_role_sets_is_staff(self):
        user = TenantUser(self._make_user_info(roles=['admin']))
        assert user.is_staff is True

    def test_superuser_role(self):
        user = TenantUser(self._make_user_info(roles=['superuser']))
        assert user.is_superuser is True

    def test_regular_user_not_staff(self):
        user = TenantUser(self._make_user_info(roles=['viewer']))
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_get_full_name(self):
        user = TenantUser(self._make_user_info(first_name='Jane', last_name='Doe'))
        assert user.get_full_name() == 'Jane Doe'

    def test_get_full_name_fallback_to_username(self):
        user = TenantUser(self._make_user_info(first_name='', last_name=''))
        assert user.get_full_name() == 'test@acme.com'

    def test_get_short_name(self):
        user = TenantUser(self._make_user_info(first_name='Jane'))
        assert user.get_short_name() == 'Jane'

    def test_has_perm_superuser(self):
        user = TenantUser(self._make_user_info(roles=['superuser']))
        assert user.has_perm('any.perm') is True

    def test_has_perm_with_matching_permission(self):
        user = TenantUser(self._make_user_info(
            permissions=['orders.view_order', 'orders.add_order']
        ))
        assert user.has_perm('orders.view_order') is True
        assert user.has_perm('orders.delete_order') is False

    def test_has_perms_all_match(self):
        user = TenantUser(self._make_user_info(
            permissions=['orders.view_order', 'orders.add_order']
        ))
        assert user.has_perms(['orders.view_order', 'orders.add_order']) is True

    def test_has_perms_partial_match_fails(self):
        user = TenantUser(self._make_user_info(
            permissions=['orders.view_order']
        ))
        assert user.has_perms(['orders.view_order', 'orders.delete_order']) is False

    def test_has_module_perms(self):
        user = TenantUser(self._make_user_info(
            permissions=['orders.view_order']
        ))
        assert user.has_module_perms('orders') is True
        assert user.has_module_perms('billing') is False

    def test_str(self):
        user = TenantUser(self._make_user_info(username='jane@acme.com'))
        assert str(user) == 'jane@acme.com'


class TestTenantAuthentication:

    def setup_method(self):
        self.auth_backend = TenantAuthentication()

    def test_returns_tenant_user_when_user_info_present(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user_info = {
            'id': '1',
            'email': 'test@acme.com',
            'username': 'test@acme.com',
            'first_name': 'Test',
            'last_name': 'User',
            'roles': ['editor'],
            'permissions': [],
        }

        result = self.auth_backend.authenticate(request)
        assert result is not None
        user, auth_info = result
        assert isinstance(user, TenantUser)
        assert user.id == '1'
        assert auth_info is None

    def test_returns_none_when_no_user_info(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')
        request.user_info = None

        result = self.auth_backend.authenticate(request)
        assert result is None

    def test_returns_none_when_user_info_not_set(self):
        factory = RequestFactory()
        request = factory.get('/api/test/')

        result = self.auth_backend.authenticate(request)
        assert result is None
