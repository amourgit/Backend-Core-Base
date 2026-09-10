"""
Migration de données : réforme "identité globale / adhésion tenant"
(e72cf35, 9 sept. 2026) -- ANNULÉE. Chaque tenant redevient autonome
pour ses utilisateurs (voir config/settings.py : 'users'/'auth'/'admin'
de nouveau double-listés SHARED_APPS + TENANT_APPS).

Exact inverse de l'ancienne adhesions.migrate_users_to_global : au lieu
de réassigner les FK du schéma vers l'id GLOBAL, on réutilise
directement cet id global comme id de la ligne locale recréée -- ces FK
(déjà réassignées vers l'id global par l'ancienne commande) restent
donc valides SANS seconde réassignation.

N'importe PAS `adhesions.models` (l'app a été supprimée avec la
réforme) : lit les tables adhesions_* restantes en SQL brut, comme
l'ancienne commande le faisait déjà pour l'ancienne table users_user
locale. Hébergée dans `tenants` (toujours un SHARED_APP, donc toujours
enregistrée) plutôt que dans `adhesions` (qui n'existe plus).

Usage :
    python manage.py migrate_users_to_tenant --schema civitasnews --dry-run
    python manage.py migrate_users_to_tenant --schema civitasnews
    python manage.py migrate_users_to_tenant --schema civitasnews --drop-adhesions-table

Prérequis : `migrate_schemas` doit avoir tourné (users/migrations/0003
recrée la table locale users_user, vide, dans ce schéma) AVANT cette
commande -- voir l'ordre dans build.sh.
Idempotent : sans effet si adhesions_membretenant n'existe pas/plus
dans ce schéma (déjà restauré, ou tenant jamais passé par la réforme --
c'est le cas de tout tenant créé après le retour de 'users' dans
TENANT_APPS, dont le schéma n'a donc jamais eu de table adhesions_*).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection

User = get_user_model()


class Command(BaseCommand):
    help = "Restaure les comptes users tenant-locaux depuis l'identité globale + adhesions_membretenant (annulation de migrate_users_to_global)."

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True, help="Nom du schéma tenant à restaurer (ex: 'civitasnews').")
        parser.add_argument('--dry-run', action='store_true', help="N'écrit rien, affiche seulement le plan.")
        parser.add_argument(
            '--drop-adhesions-table', action='store_true',
            help="Supprime les tables adhesions_* de ce schéma une fois la restauration validée.",
        )

    def handle(self, *args, **options):
        schema = options['schema'].strip().lower()
        dry_run = options['dry_run']

        if not self._table_existe(schema, 'adhesions_membretenant'):
            self.stdout.write(self.style.WARNING(
                f"Aucune table adhesions_membretenant dans '{schema}' -- rien à restaurer "
                f"(déjà fait, ou tenant jamais passé par la réforme identité globale)."
            ))
            return

        if not self._table_existe(schema, 'users_user'):
            self.stdout.write(self.style.ERROR(
                f"Table users_user locale absente de '{schema}' -- lancez migrate_schemas "
                f"(avec 'users' de retour dans TENANT_APPS) AVANT cette commande."
            ))
            return

        membres = self._lire_membres(schema)
        self.stdout.write(f"{len(membres)} adhésion(s) trouvée(s) dans '{schema}'.")

        comptes_globaux = {u.id: u for u in User.objects.filter(id__in=[m['user_id'] for m in membres])}

        if dry_run:
            for m in membres:
                compte = comptes_globaux.get(m['user_id'])
                self.stdout.write(
                    f"  global#{m['user_id']} ({compte.username if compte else '???'}) "
                    f"-> {schema}#{m['user_id']} (role={m['role']})"
                )
            self.stdout.write(self.style.WARNING("--dry-run : aucune écriture effectuée."))
            return

        nb = self._recreer_comptes_locaux(schema, membres, comptes_globaux)
        self.stdout.write(self.style.SUCCESS(f"✅ {nb} compte(s) local(aux) restauré(s) sur '{schema}'."))

        if options['drop_adhesions_table']:
            self._supprimer_tables_adhesions(schema)
            self.stdout.write(self.style.SUCCESS(f"✅ Table(s) adhesions_* supprimée(s) pour '{schema}'."))

    # -- Helpers SQL bruts (adhesions n'existe plus comme app Django) ----

    def _table_existe(self, schema, table):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                [schema, table],
            )
            return cur.fetchone()[0]

    def _lire_membres(self, schema):
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute(
                "SELECT user_id, role, organisation_id, etablissement_id FROM adhesions_membretenant ORDER BY user_id"
            )
            colonnes = [c.name for c in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
            cur.execute("SET search_path TO public")
        return lignes

    def _recreer_comptes_locaux(self, schema, membres, comptes_globaux):
        """Recrée chaque compte DANS le schéma tenant, en réutilisant l'ID
        GLOBAL comme id de la ligne locale -- les FK du schéma qui
        référencent déjà cet id (réassignées par migrate_users_to_global
        en son temps) restent valides sans y retoucher."""
        nb = 0
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            for m in membres:
                compte = comptes_globaux.get(m['user_id'])
                if compte is None:
                    self.stdout.write(self.style.WARNING(f"  compte global#{m['user_id']} introuvable, ignoré."))
                    continue
                cur.execute(
                    "INSERT INTO users_user (id, password, last_login, is_superuser, username, "
                    "first_name, last_name, is_staff, is_active, date_joined, email, phone_number, "
                    "address, date_of_birth, is_verified, language_preference, timezone, "
                    "role, etablissement_id, organisation_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO NOTHING",
                    [
                        compte.id, compte.password, compte.last_login, compte.is_superuser, compte.username,
                        compte.first_name, compte.last_name, compte.is_staff, compte.is_active, compte.date_joined,
                        compte.email, compte.phone_number, compte.address, compte.date_of_birth,
                        compte.is_verified, compte.language_preference, compte.timezone,
                        m['role'], m['etablissement_id'], m['organisation_id'],
                    ],
                )
                nb += 1
            # Les INSERT explicites ci-dessus n'avancent pas la séquence PK :
            # la resynchroniser pour que les prochaines créations locales
            # (superuser via bootstrap_tenant, inscriptions...) ne
            # collisionnent pas avec les id restaurés.
            cur.execute(
                "SELECT setval(pg_get_serial_sequence('users_user', 'id'), "
                "COALESCE((SELECT MAX(id) FROM users_user), 1))"
            )
            self._migrer_badges(cur, schema)
            cur.execute("SET search_path TO public")
        return nb

    def _migrer_badges(self, cur, schema):
        """adhesions_badge (+ M2M adhesions_membretenant_badges) ->
        users_badge (+ M2M users_user_badges), apparié par nom."""
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'adhesions_badge')",
            [schema],
        )
        if not cur.fetchone()[0]:
            return
        cur.execute("SELECT id, nom, icone, description FROM adhesions_badge")
        mapping_badge = {}
        for old_id, nom, icone, description in cur.fetchall():
            cur.execute("SELECT id FROM users_badge WHERE nom = %s", [nom])
            row = cur.fetchone()
            if row:
                mapping_badge[old_id] = row[0]
            else:
                cur.execute(
                    "INSERT INTO users_badge (nom, icone, description) VALUES (%s, %s, %s) RETURNING id",
                    [nom, icone, description],
                )
                mapping_badge[old_id] = cur.fetchone()[0]

        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = 'adhesions_membretenant_badges')",
            [schema],
        )
        if cur.fetchone()[0]:
            cur.execute(
                "SELECT mt.user_id, amb.badge_id FROM adhesions_membretenant_badges amb "
                "JOIN adhesions_membretenant mt ON mt.id = amb.membretenant_id"
            )
            for user_id, old_badge_id in cur.fetchall():
                badge_id = mapping_badge.get(old_badge_id)
                if badge_id:
                    cur.execute(
                        "INSERT INTO users_user_badges (user_id, badge_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        [user_id, badge_id],
                    )

    def _supprimer_tables_adhesions(self, schema):
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            for table in ('adhesions_membretenant_badges', 'adhesions_membretenant', 'adhesions_badge'):
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            cur.execute("DELETE FROM django_migrations WHERE app = 'adhesions'")
            cur.execute("SET search_path TO public")
