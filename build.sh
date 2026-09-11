#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate_schemas --shared

python manage.py migrate_schemas

# ⚠️ Migrations remises à zéro (commit "suppression de tous les fichiers
# de migrations", 11 sept. 2026) : chaque app n'a plus qu'un seul
# 0001_initial reflétant l'état actuel des modèles (users.User inclut
# déjà role/etablissement/organisation/badges dès ce 0001 -- plus de
# 0002/0003 historiques). Sur une base de données QUI A DÉJÀ TOURNÉ
# avec l'ancien historique (ex: le tenant "civitasnews" en prod, dont
# le django_migrations référence des migrations qui n'existent plus
# dans le code), `migrate_schemas` ci-dessus échouera ou divergera tant
# que cette base n'a pas été réinitialisée ou réconciliée à la main
# (ex: `migrate --fake` vers ce nouveau 0001, ou schéma recréé propre)
# -- à confirmer/faire AVANT ce déploiement pour civitasnews.
#
# Réforme identité globale / adhésion tenant ANNULÉE (voir
# tenants/management/commands/migrate_users_to_tenant.py) : chaque
# tenant redevient autonome pour ses utilisateurs. Une fois la base de
# "civitasnews" réconciliée avec le nouveau 0001_initial (users_user
# locale existante), cette commande la repeuple depuis l'identité
# globale + adhesions_membretenant si elle existe encore, puis supprime
# les tables adhesions_* devenues orphelines. Idempotent et sans effet
# si déjà fait ou jamais nécessaire (se contente de logguer et sortir
# si adhesions_membretenant n'existe pas/plus) -- donc sûr de rappeler
# à chaque déploiement.
python manage.py migrate_users_to_tenant --schema civitasnews --drop-adhesions-table
