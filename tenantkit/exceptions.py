"""
All exceptions for tenantkit.

    from tenantkit.exceptions import AuthenticationError, TenantRequiredError
"""

from rest_framework.exceptions import ValidationError


# --- Authentication ---

class AuthenticationError(Exception):
    """Invalid/expired token or user not found."""

class AuthorizationError(Exception):
    """Authenticated user lacks required permissions."""

class AuthServiceError(Exception):
    """Auth service unavailable or returned an unexpected error."""

class UserBlockedError(Exception):
    """Blocked user attempted to authenticate."""


# --- Tenancy ---

class TenantRequiredError(ValidationError):
    """Tenant context required but not present."""
    default_detail = "Tenant context required"
    default_code = "TENANT_REQUIRED"

class TenantNotFoundError(Exception):
    """Tenant could not be resolved from the request."""

class TenantSwitchError(Exception):
    """Switching to a tenant schema/database failed."""
