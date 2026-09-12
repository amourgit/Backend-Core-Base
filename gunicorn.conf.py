"""
Configuration gunicorn.

Contexte : POST /api/tenants/v1/ (création d'un tenant) crée un schéma
Postgres et lui applique TOUTES les migrations de l'app (voir
Tenant.create_with_domain / auto_create_schema=True, tenants/models.py)
de façon SYNCHRONE, dans le cycle requête/réponse. Le timeout par défaut
de gunicorn (30s, worker sync) est trop court pour ça sur les
ressources limitées du plan gratuit Render : le worker se fait tuer
(WORKER TIMEOUT -> SIGKILL) en pleine migration, ce qui laisse la
requête en 500 et peut laisser un schéma à moitié créé.

`timeout` ci-dessous relève cette limite. Root cause déjà réduite côté
tenants/models.py (suppression d'une double-migration redondante qui
faisait tourner ce travail deux fois), mais une marge de sécurité reste
nécessaire tant que cette opération reste synchrone.

IMPORTANT (à faire une seule fois, hors dépôt) : ce fichier n'est
appliqué QUE si la Start Command de Render invoque gunicorn avec
`-c gunicorn.conf.py`, par exemple :

    gunicorn config.wsgi:application -c gunicorn.conf.py

Alternative sans toucher à la Start Command : définir la variable
d'environnement `GUNICORN_CMD_ARGS=--timeout 300` dans les paramètres
du service sur Render (Environment). Gunicorn la lit automatiquement.
"""

# Délai (s) avant qu'un worker inactif sur une requête ne soit tué et
# relancé. 300s laisse largement la place à la création d'un tenant
# même sur des ressources lentes, sans pour autant masquer un vrai
# blocage indéfini.
timeout = 300

# Délai de grâce laissé à un worker pour terminer proprement au reload/
# redéploiement avant d'être forcé.
graceful_timeout = 30

# Nombre de workers : formule standard (2 x CPU + 1). Sur le plan
# gratuit Render (1 CPU partagé), 2 est un choix raisonnable ; à ajuster
# selon la charge réelle plutôt que de le sur-dimensionner.
workers = 2

# Loggue sur stdout/stderr, cohérent avec la façon dont Render capture
# les logs (pas de fichier local à faire tourner soi-même).
accesslog = "-"
errorlog = "-"
