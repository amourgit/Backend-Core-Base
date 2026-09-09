#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate_schemas --shared

python manage.py migrate_schemas

# Réforme identité globale / adhésion tenant (voir adhesions/management/
# commands/migrate_users_to_global.py) : bascule les comptes tenant-locaux
# pré-réforme du tenant "civitasnews" vers l'identité globale + crée les
# adhesions.MembreTenant correspondantes, puis supprime la table users_user
# locale devenue orpheline. Idempotent et sans effet si déjà fait (la
# commande se contente de logguer et de sortir si la table locale n'existe
# plus) -- donc sûr de rappeler à chaque déploiement.
python manage.py migrate_users_to_global --schema civitasnews --drop-local-table
