"""
Tenant and Domain mixins that wrap django-tenants' mixins.

Projects should import from here instead of django_tenants.models:

    from tenantkit.tenancy.models import TenantMixin, DomainMixin

In schema mode, save() delegates to django-tenants (creates schema).
In database mode, save() creates a separate PostgreSQL database instead.
"""

import logging

from django_tenants.models import (
    TenantMixin as BaseTenantMixin,
    DomainMixin as BaseDomainMixin,
)

logger = logging.getLogger(__name__)


class TenantMixin(BaseTenantMixin):
    """
    Drop-in replacement for django_tenants.models.TenantMixin.

    Adds database-per-tenant support on save() and delete().
    """

    class Meta:
        abstract = True

    def save(self, verbosity=1, *args, **kwargs):
        from tenantkit.conf import settings as tk

        if tk.TENANT_DB_MODE != 'database':
            # Schema mode — let django-tenants handle everything
            return super().save(verbosity=verbosity, *args, **kwargs)

        # Database mode — prevent django-tenants from creating a schema
        is_new = self._state.adding
        original_auto_create = self.auto_create_schema
        self.auto_create_schema = False

        try:
            super().save(verbosity=verbosity, *args, **kwargs)
        finally:
            self.auto_create_schema = original_auto_create

        if is_new and original_auto_create:
            from tenantkit.tenancy.backends import get_backend
            backend = get_backend()

            result = backend.create_tenant(self.schema_name)
            if not result.get('success'):
                self.delete(force_drop=True)
                raise Exception(
                    f"Failed to create tenant database: {result.get('error')}"
                )

            migration_result = backend.run_migrations(self.schema_name)
            if not migration_result.get('success'):
                # Roll back: drop the database and the saved row
                backend.destroy_tenant(self.schema_name)
                self.delete(force_drop=True)
                raise Exception(
                    f"Migrations failed for tenant '{self.schema_name}': "
                    f"{migration_result.get('error')}"
                )

    def delete(self, force_drop=False, *args, **kwargs):
        from tenantkit.conf import settings as tk

        if tk.TENANT_DB_MODE != 'database':
            # Schema mode — let django-tenants handle it
            return super().delete(force_drop=force_drop, *args, **kwargs)

        # Database mode — drop the database if auto_drop_schema or force_drop
        if self.auto_drop_schema or force_drop:
            from tenantkit.tenancy.backends import get_backend
            backend = get_backend()
            backend.destroy_tenant(self.schema_name)

        # Skip django-tenants' schema drop logic
        original_auto_drop = self.auto_drop_schema
        self.auto_drop_schema = False
        try:
            return super().delete(force_drop=False, *args, **kwargs)
        finally:
            self.auto_drop_schema = original_auto_drop


class DomainMixin(BaseDomainMixin):
    """
    Drop-in replacement for django_tenants.models.DomainMixin.

    Currently identical — exists so projects only import from tenantkit.
    """

    class Meta:
        abstract = True
