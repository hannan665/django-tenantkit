"""
Abstract base class for tenant backends.
"""

import re
from abc import ABC, abstractmethod
from typing import List, Optional

from tenantkit.tenancy.context import get_current_tenant, get_current_db_alias

_SAFE_NAME_RE = re.compile(r'^[a-z0-9_-]+$')


def validate_tenant_name(name: str) -> None:
    """Raise ValueError if name contains characters unsafe for SQL identifiers."""
    if not name or not _SAFE_NAME_RE.match(name):
        raise ValueError(
            f"Invalid tenant name '{name}': must contain only lowercase letters, "
            "digits, hyphens, and underscores."
        )


class BaseTenantBackend(ABC):

    @abstractmethod
    def activate(self, tenant_name: str) -> None:
        """Activate tenant context (set schema or register DB)."""

    @abstractmethod
    def deactivate(self) -> None:
        """Clean up after request (close connections, reset schema)."""

    @abstractmethod
    def create_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        """Provision storage for a new tenant."""

    @abstractmethod
    def destroy_tenant(self, tenant_name: str, using: str = 'default') -> dict:
        """Remove a tenant's storage."""

    @abstractmethod
    def run_migrations(self, tenant_name: str) -> dict:
        """Run migrations for a single tenant."""

    @abstractmethod
    def run_all_migrations(self) -> dict:
        """Run migrations for every tenant."""

    @abstractmethod
    def get_all_tenants(self) -> List[str]:
        """Return a list of all tenant identifiers."""

    @abstractmethod
    def get_db_alias(self, tenant_name: str) -> str:
        """Return the Django DATABASES alias for the given tenant."""

    # -- concrete helpers ------------------------------------------------

    def get_db_alias_for_current(self) -> Optional[str]:
        """Return the DB alias for the current context's tenant."""
        db_alias = get_current_db_alias()
        if db_alias:
            return db_alias

        tenant_name = get_current_tenant()
        if not tenant_name:
            return None
        return self.get_db_alias(tenant_name)
