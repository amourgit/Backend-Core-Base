"""
Migration de données : réforme identité globale / adhésion tenant.

Avant cette réforme, `users` était doublé SHARED_APPS + TENANT_APPS :
chaque tenant avait sa PROPRE table `users_user`, isolée. Cette
commande, À LANCER UNE FOIS PAR TENANT EXISTANT (avant la réforme),
migre ces comptes locaux vers l'identité globale (schéma public) et
crée l'adhésion (adhesions.MembreTenant) correspondante dans ce tenant,
en réassignant au passage TOUTES les colonnes FK du schéma qui
référençaient l'ancienne table locale `users_user` (`cree_par_id`,
`auteur_id`, etc. -- découverte dynamique via les contraintes FK
Postgres, pas de liste de tables en dur).

Usage :
    python manage.py migrate_users_to_global --schema moncampus --dry-run
    python manage.py migrate_users_to_global --schema moncampus
    python manage.py migrate_users_to_global --schema moncampus --drop-local-table

Ordre attendu : lancer d'abord SANS --drop-local-table sur chaque
tenant existant, vérifier, puis relancer avec --drop-local-table une
fois validé (supprime alors la table locale devenue orpheline).
Idempotent tant que --drop-local-table n'a pas encore été exécuté :
peut être relancée sans dupliquer les comptes globaux déjà appariés
(par email/téléphone) ni les adhésions déjà créées.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django_tenants.utils import schema_context

from adhesions.models import MembreTenant, Badge

User = get_user_model()


class Command(BaseCommand):
    help = "Migre les comptes users tenant-locaux (pré-réforme) vers l'identité globale + adhesions.MembreTenant."

    def add_arguments(self, parser):
        parser.add_argument('--schema', required=True, help="Nom du schéma tenant à migrer (ex: 'moncampus').")
        parser.add_argument('--dry-run', action='store_true', help="N'écrit rien, affiche seulement le plan de migration.")
        parser.add_argument(
            '--drop-local-table', action='store_true',
            help="Supprime la table users_user locale (et auth/admin locaux orphelins) de ce schéma une fois la migration validée.",
        )

    def handle(self, *args, **options):
        schema = options['schema'].strip().lower()
        dry_run = options['dry_run']

        if not self._table_existe(schema, 'users_user'):
            self.stdout.write(self.style.WARNING(
                f"Aucune table users_user locale dans le schéma '{schema}' -- rien à migrer (déjà fait, ou tenant créé après la réforme)."
            ))
            return

        lignes_locales = self._lire_lignes_locales(schema)
        self.stdout.write(f"{len(lignes_locales)} compte(s) local(aux) trouvé(s) dans '{schema}'.")

        mapping = {}  # ancien id local (ce schéma) -> id global (public)
        with schema_context('public'):
            for ligne in lignes_locales:
                utilisateur = self._trouver_ou_creer_global(ligne, dry_run=dry_run)
                mapping[ligne['id']] = utilisateur.id if utilisateur else None
                self.stdout.write(f"  {schema}#{ligne['id']} ({ligne['username']!r}) -> global#{mapping[ligne['id']]}")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run : aucune écriture effectuée."))
            return

        with schema_context(schema):
            with transaction.atomic():
                for ligne in lignes_locales:
                    user_id = mapping[ligne['id']]
                    if user_id is None:
                        continue
                    membre, _created = MembreTenant.objects.get_or_create(
                        user_id=user_id,
                        defaults=dict(
                            role=ligne['role'] or 'etudiant',
                            organisation_id=ligne['organisation_id'],
                            etablissement_id=ligne['etablissement_id'],
                        ),
                    )
                self._migrer_badges(schema, mapping)

        nb_fk = self._reassigner_fk_vers_global(schema, mapping)
        self.stdout.write(self.style.SUCCESS(
            f"✅ {len(lignes_locales)} compte(s) migré(s), {nb_fk} colonne(s) FK réassignée(s) vers l'identité globale sur '{schema}'."
        ))

        if options['drop_local_table']:
            self._supprimer_tables_locales(schema)
            self.stdout.write(self.style.SUCCESS(f"✅ Table(s) users/auth/admin locale(s) supprimée(s) pour '{schema}'."))

    # -- Helpers SQL bruts (la table locale n'est plus modélisée par l'ORM
    # -- `users.User` ne pointe plus que sur le schéma public) -----------

    def _table_existe(self, schema, table):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                [schema, table],
            )
            return cur.fetchone()[0]

    def _lire_lignes_locales(self, schema):
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute(
                "SELECT id, username, email, phone_number, first_name, last_name, password, "
                "is_active, is_staff, is_superuser, is_verified, date_joined, last_login, "
                "address, date_of_birth, language_preference, timezone, role, "
                "etablissement_id, organisation_id FROM users_user ORDER BY id"
            )
            colonnes = [c.name for c in cur.description]
            lignes = [dict(zip(colonnes, row)) for row in cur.fetchall()]
            cur.execute("SET search_path TO public")
        return lignes

    def _trouver_ou_creer_global(self, ligne, dry_run):
        """Apparie par email puis téléphone (mêmes identifiants de connexion
        uniques qu'aujourd'hui) ; sinon crée un nouveau compte global,
        username désambiguïsé en cas de collision entre tenants."""
        utilisateur = None
        if ligne['email']:
            utilisateur = User.objects.filter(email=ligne['email']).first()
        if utilisateur is None and ligne['phone_number']:
            utilisateur = User.objects.filter(phone_number=ligne['phone_number']).first()
        if utilisateur is not None or dry_run:
            return utilisateur

        username = ligne['username']
        base, suffixe = username, 1
        while User.objects.filter(username=username).exists():
            suffixe += 1
            username = f"{base}{suffixe}"
        return User.objects.create(
            username=username, email=ligne['email'], phone_number=ligne['phone_number'],
            first_name=ligne['first_name'] or '', last_name=ligne['last_name'] or '',
            password=ligne['password'],  # déjà hashé (PBKDF2/argon2 Django) -- réutilisable tel quel
            is_active=ligne['is_active'], is_staff=ligne['is_staff'], is_superuser=ligne['is_superuser'],
            is_verified=ligne['is_verified'], date_joined=ligne['date_joined'], last_login=ligne['last_login'],
            address=ligne['address'] or '', date_of_birth=ligne['date_of_birth'],
            language_preference=ligne['language_preference'] or 'en', timezone=ligne['timezone'] or 'UTC',
        )

    def _migrer_badges(self, schema, mapping):
        """Porte le catalogue users_badge -> adhesions_badge (apparié par
        nom, créé si absent) et la M2M users_user_badges ->
        adhesions_membretenant_badges."""
        if not self._table_existe(schema, 'users_badge'):
            return
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            cur.execute("SELECT id, nom, icone, description FROM users_badge")
            badges_locaux = cur.fetchall()
            mapping_badge = {}
            for old_id, nom, icone, description in badges_locaux:
                badge, _ = Badge.objects.get_or_create(nom=nom, defaults={'icone': icone, 'description': description or ''})
                mapping_badge[old_id] = badge.id

            if self._table_existe(schema, 'users_user_badges'):
                cur.execute("SELECT user_id, badge_id FROM users_user_badges")
                for old_user_id, old_badge_id in cur.fetchall():
                    user_id = mapping.get(old_user_id)
                    badge_id = mapping_badge.get(old_badge_id)
                    if user_id and badge_id:
                        membre = MembreTenant.objects.filter(user_id=user_id).first()
                        if membre:
                            membre.badges.add(badge_id)
            cur.execute("SET search_path TO public")

    def _reassigner_fk_vers_global(self, schema, mapping):
        """Découvre dynamiquement toutes les colonnes FK du schéma qui
        référencent encore l'ancienne table locale `users_user`
        (cree_par_id, modifie_par_id, auteur_id, etc. -- SocleTracabilite
        et FKs directes), et réassigne leurs valeurs vers l'ID global
        correspondant."""
        with connection.cursor() as cur:
            cur.execute(
                "SELECT tc.table_name, kcu.column_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s "
                "  AND ccu.table_name = 'users_user' AND ccu.table_schema = %s",
                [schema, schema],
            )
            colonnes = [row for row in cur.fetchall() if row[0] != 'users_user']

            cur.execute(f'SET search_path TO "{schema}"')
            for table_name, column_name in colonnes:
                for ancien_id, nouveau_id in mapping.items():
                    if nouveau_id is None:
                        continue
                    cur.execute(
                        f'UPDATE "{table_name}" SET "{column_name}" = %s WHERE "{column_name}" = %s',
                        [nouveau_id, ancien_id],
                    )
            cur.execute("SET search_path TO public")
        return len(colonnes)

    def _supprimer_tables_locales(self, schema):
        with connection.cursor() as cur:
            cur.execute(f'SET search_path TO "{schema}"')
            for table in (
                'users_user_badges', 'users_user_user_permissions', 'users_user_groups',
                'users_badge', 'django_admin_log', 'auth_group_permissions',
                'auth_permission', 'auth_group', 'users_user',
            ):
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            cur.execute("DELETE FROM django_migrations WHERE app IN ('users', 'auth', 'admin')")
            cur.execute("SET search_path TO public")
