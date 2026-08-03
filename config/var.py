"""
Valeurs par défaut liées aux tokens.

ATTENTION : ce fichier était auparavant dangereux à importer. Il exécutait
une requête base de données (TokenSettings.get_active_settings()) au niveau
module, donc AU MOMENT DE L'IMPORT — avant que les migrations existent ou
que le schéma tenant soit résolu. Si aucune ligne TokenSettings active
n'existait, `settings_token_actif.access_token_lifetime` levait une
AttributeError sur None et faisait planter tout le processus qui importait
ce module.

Les valeurs réellement utilisées en pratique viennent de
token_manager/apps.py::TokenManagerConfig.ready(), qui charge la config
active de façon sûre (avec try/except) pendant la phase de démarrage de
Django. Ce module ne fait plus que fournir des valeurs de repli statiques ;
il n'exécute plus aucune requête à l'import.
"""

# Valeurs de repli statiques (en minutes), utilisées uniquement si aucune
# configuration dynamique n'est disponible.
LIFETIMME_ACCESS_TOKEN = 5
LIFETIMME_REFRESH_TOKEN = 10


def get_active_token_settings():
    """
    Accesseur paresseux et sûr vers TokenSettings.get_active_settings().
    À utiliser à la place de l'ancien code exécuté à l'import : n'effectue
    la requête que lorsqu'on l'appelle réellement, et ne plante jamais.
    """
    from token_manager.models import TokenSettings

    try:
        return TokenSettings.get_active_settings()
    except Exception:
        return None
