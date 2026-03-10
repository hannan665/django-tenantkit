"""Tests for tenantkit.exceptions."""

import pytest

from tenantkit.exceptions import (
    AuthenticationError,
    AuthorizationError,
    AuthServiceError,
    UserBlockedError,
    TenantRequiredError,
    TenantNotFoundError,
    TenantSwitchError,
)


class TestExceptions:

    def test_authentication_error(self):
        with pytest.raises(AuthenticationError, match='bad token'):
            raise AuthenticationError('bad token')

    def test_authorization_error(self):
        with pytest.raises(AuthorizationError):
            raise AuthorizationError('not allowed')

    def test_auth_service_error(self):
        with pytest.raises(AuthServiceError):
            raise AuthServiceError('service down')

    def test_user_blocked_error(self):
        with pytest.raises(UserBlockedError):
            raise UserBlockedError('blocked')

    def test_tenant_required_error(self):
        with pytest.raises(TenantRequiredError):
            raise TenantRequiredError()

    def test_tenant_not_found_error(self):
        with pytest.raises(TenantNotFoundError):
            raise TenantNotFoundError('no such tenant')

    def test_tenant_switch_error(self):
        with pytest.raises(TenantSwitchError):
            raise TenantSwitchError('switch failed')

    def test_tenant_required_has_default_detail(self):
        err = TenantRequiredError()
        assert 'Tenant context required' in str(err.detail)
