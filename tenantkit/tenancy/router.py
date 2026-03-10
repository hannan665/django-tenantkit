"""
Django database router for multi-tenant apps.
"""

from tenantkit.conf import settings as tk
from tenantkit.tenancy.backends import get_backend


class TenantDatabaseRouter:

    def __init__(self):
        self.tenant_apps = tk.TENANT_APPS
        self.shared_apps = tk.SHARED_APPS
        self.tenant_model_apps = tk.TENANT_MODEL_APPS

    def db_for_read(self, model, **hints):
        return self._route(model)

    def db_for_write(self, model, **hints):
        return self._route(model)

    def allow_relation(self, obj1, obj2, **hints):
        a1 = obj1._meta.app_label
        a2 = obj2._meta.app_label

        if a1 in self.shared_apps and a2 in self.shared_apps:
            return True
        if a1 in self.tenant_apps and a2 in self.tenant_apps:
            return True
        if (a1 in self.tenant_apps and a2 in self.shared_apps) or \
           (a1 in self.shared_apps and a2 in self.tenant_apps):
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in self.shared_apps or app_label in self.tenant_model_apps:
            return db == 'default'

        if app_label in self.tenant_apps:
            if tk.TENANT_DB_MODE == 'database':
                return db != 'default'
            return True

        return db == 'default'

    # -- internal --------------------------------------------------------

    def _route(self, model):
        app = model._meta.app_label

        if app in self.shared_apps or app in self.tenant_model_apps:
            return 'default'

        if app in self.tenant_apps:
            alias = get_backend().get_db_alias_for_current()
            if alias is None:
                from tenantkit.exceptions import TenantRequiredError
                raise TenantRequiredError(
                    f"No tenant context available for app '{app}'. "
                    "Ensure TenantMiddleware has activated a tenant before querying tenant models."
                )
            return alias

        return None
