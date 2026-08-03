from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'
    verbose_name = 'Gestion des Tenants'

    # def ready(self):
    #     import tenants.api.v1.signals
