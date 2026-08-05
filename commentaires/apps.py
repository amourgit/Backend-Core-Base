from django.apps import AppConfig


class CommentairesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'commentaires'
    verbose_name = 'Commentaires'

    def ready(self):
        from . import signals  # noqa: F401 — enregistre les récepteurs de signaux
