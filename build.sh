#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

# ⚠️ Migrations non committées (voir .gitignore) : générées à neuf ICI,
# à CHAQUE déploiement, à partir de l'état actuel des modèles -- jamais
# incrémentales. Tant que les modèles ne changent pas entre deux
# déploiements, cette régénération reproduit un 0001_initial identique
# et migrate_schemas la trouve déjà appliquée (par nom) : sans effet,
# comme prévu. MAIS le jour où un modèle change entre deux déploiements
# sur une base qui a DÉJÀ des données (ex: le tenant civitasnews) :
# le nouveau champ arrive fondu DANS ce même 0001_initial (jamais un
# 0002_ séparé, puisqu'aucun historique n'est conservé) -- Django voit
# '0001_initial' déjà appliqué par son nom et ne rejoue PAS l'opération
# manquante, donc ne crée PAS la colonne en base. Migrations
# non-committées = schéma toujours regénérable, mais jamais d'évolution
# incrémentale sûre sur une base existante -- seulement viable tant que
# chaque changement de modèle s'accompagne d'une base repartie à zéro.
python manage.py makemigrations --no-input

python manage.py migrate_schemas --shared

python manage.py migrate_schemas

# Sur civitasnews (déjà en prod avec l'ANCIEN historique de migrations,
# avant qu'il ne soit retiré du dépôt) : le migrate_schemas ci-dessus
# échouera ou divergera tant que sa base n'a pas été réinitialisée ou
# réconciliée à la main (`migrate --fake` vers ce 0001_initial, ou
# schéma recréé propre) -- à confirmer/faire AVANT ce déploiement.
#
# Réforme identité globale / adhésion tenant ANNULÉE (voir
# tenants/management/commands/migrate_users_to_tenant.py) : chaque
# tenant redevient autonome pour ses utilisateurs. Une fois la base de
# "civitasnews" réconciliée avec le 0001_initial ci-dessus (users_user
# locale existante), cette commande la repeuple depuis l'identité
# globale + adhesions_membretenant si elle existe encore, puis supprime
# les tables adhesions_* devenues orphelines. Idempotent et sans effet
# si déjà fait ou jamais nécessaire (se contente de logguer et sortir
# si adhesions_membretenant n'existe pas/plus) -- donc sûr de rappeler
# à chaque déploiement.
python manage.py migrate_users_to_tenant --schema civitasnews --drop-adhesions-table
