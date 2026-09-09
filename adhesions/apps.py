from django.apps import AppConfig


class AdhesionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adhesions'
    verbose_name = "Adhésions (représentation tenant d'un utilisateur global)"
