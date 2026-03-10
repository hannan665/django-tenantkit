from django.apps import AppConfig


class TenantKitConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenantkit'
    verbose_name = 'TenantKit'
