from django.apps import AppConfig
from django.conf import settings


class TokenManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "token_manager"
    verbose_name = 'Gestionnaire de jetons'

    def ready(self):
        # import token_manager.api.v1.signals  # noqa
        
        # Chargement des paramètres JWT personnalisés
        try:
            from .token_settings import get_token_settings
            custom_settings = get_token_settings()
            if custom_settings:
                settings.SIMPLE_JWT.update(custom_settings)
                print("Paramètres JWT mis à jour avec succès depuis la base de données")
        except ImportError:
            print("Le module token_settings n'a pas été trouvé")
        except Exception as e:
            print(f"Erreur lors du chargement des paramètres JWT : {e}")
