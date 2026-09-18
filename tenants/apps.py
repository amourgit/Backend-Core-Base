from django.apps import AppConfig


class TenantsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tenants'
    verbose_name = 'Gestion des Tenants'

    def ready(self):
        # Enregistre les récepteurs d'invalidation du cache de résolution
        # tenant (voir tenants/signals.py -- jamais câblé jusqu'ici, ce
        # `ready()` était entièrement commenté et pointait de toute façon
        # vers le mauvais module, tenants/api/v1/signals.py, qui ne
        # contient qu'un récepteur laissé en commentaire).
        import tenants.signals  # noqa: F401
