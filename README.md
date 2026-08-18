
```bash
# 1. Clone du repo
git clone https://github.com/ioi-101/EDUNET_GABON.git
cd EDUNET_GABON

# 2. Création environnement
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configuration .env
cp .env.example .env
# Modifier les infos DB, SECRET_KEY, MAIN_DOMAIN, etc.

# 4. Initialisation
python manage.py migrate_schemas --shared
python manage.py createsuperuser

# 5. Lancer le serveur
python manage.py runserver
```

## Amorçage complet (admin plateforme + tenant + admin tenant), non-interactif

Les 3 commandes ci-dessous remplacent entièrement l'ancien flux manuel
(`create_tenant` interactif + `manage.py shell`) : tous les paramètres
sont passés en ligne de commande, rien ne demande de saisie humaine --
adapté à un déploiement où le shell n'est pas disponible (ex: Render en
plan gratuit), en les enchaînant après les migrations, avant la commande
de démarrage du serveur.

Idempotentes : peuvent être relancées sans effet de bord à chaque
redéploiement (elles ne recréent rien si le tenant/l'utilisateur existe
déjà).

```bash
# 1. Migrations du schéma public (déjà fait par build.sh)
python manage.py migrate_schemas --shared

# 2. Administrateur PLATEFORME (schéma public) -- gère les Tenants/Domains
python manage.py bootstrap_public --create-superuser \
    --username <username> --email <email> --password "<mot-de-passe>"

# 3. Tenant "établissement" + son domaine + son administrateur
#    --extra-domain : nécessaire si le frontend n'est PAS hébergé en
#    sous-domaine du backend (ex: frontend Vercel, backend Render --
#    voir tenants/middleware.py:TenantMiddleware.is_valid_domain).
python manage.py bootstrap_tenant \
    --nom "<Nom affiché>" --sous-domaine <sous-domaine> \
    --extra-domain <domaine-du-frontend> \
    --create-admin --admin-username <username> \
    --admin-email <email> --admin-password "<mot-de-passe>"
```

Détails et toutes les options : `python manage.py bootstrap_public --help`
et `python manage.py bootstrap_tenant --help` (voir aussi les docstrings
en tête de `tenants/management/commands/bootstrap_public.py` et
`bootstrap_tenant.py`).

## Dev local avec Docker

```bash
# Arrêter PostgreSQL et supprimer le volume (dev local avec Docker)
docker compose down -v

# Redémarrer PostgreSQL
docker compose up -d

# Supprimer les fichiers de migrations (conserver __init__.py)
find */migrations -name "*.py" ! -name "__init__.py" -delete

# Recréer les migrations
python manage.py makemigrations

# Exécuter les migrations partagées
python manage.py migrate_schemas --shared

# Exécuter les migrations tenant
python manage.py migrate_schemas
```

Pour la création du tenant et de ses administrateurs, voir la section
"Amorçage complet" ci-dessus -- `bootstrap_public` et `bootstrap_tenant`
remplacent l'ancien flux `create_tenant` (interactif) + `manage.py shell`.
