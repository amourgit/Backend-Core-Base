#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate_schemas --shared

python manage.py migrate_schemas

# Réforme identité globale / adhésion tenant ANNULÉE (voir
# tenants/management/commands/migrate_users_to_tenant.py) : chaque
# tenant redevient autonome pour ses utilisateurs. migrate_schemas
# ci-dessus a déjà recréé une table users_user locale VIDE pour
# "civitasnews" (users/migrations/0003_restaure_...) ; cette commande
# la repeuple depuis l'identité globale + adhesions_membretenant, puis
# supprime les tables adhesions_* devenues orphelines. Idempotent et
# sans effet si déjà fait (se contente de logguer et sortir si
# adhesions_membretenant n'existe plus) -- donc sûr de rappeler à
# chaque déploiement.
python manage.py migrate_users_to_tenant --schema civitasnews --drop-adhesions-table
