"""
Commande d'amorçage d'un tenant "établissement" de développement/démo.

`bootstrap_public` crée le tenant PUBLIC (admin plateforme), mais rien
n'existait pour créer facilement un tenant "établissement" avec son
propre schéma et son propre sous-domaine -- pourtant indispensable pour
tester quoi que ce soit côté CIVITAS NEWS (news, commentaires, sondages,
liens, notifications, journal, moderation, statistiques ne vivent QUE
dans un schéma tenant, jamais dans le schéma public : voir le correctif
"tenant réel requis" dans tenants/middleware.py). Sans un tel tenant,
TOUTE requête vers ces apps échoue -- soit en 500 brute avant ce
correctif, soit en 400 "TENANT_REQUIRED" clair après, mais échoue dans
les deux cas si elle est appelée sur le domaine racine faute de tenant
réel disponible pour la router.

Usage :
    python manage.py bootstrap_tenant --nom "Mon Campus" --sous-domaine moncampus
    python manage.py bootstrap_tenant --nom "Mon Campus" --sous-domaine moncampus \
        --extra-domain civitasnews.vercel.app \
        --create-admin --admin-username admin --admin-email admin@moncampus.example \
        --admin-password "un-mot-de-passe-fort"

Avec auto_create_schema=True sur le modèle Tenant (voir tenants/models.py),
la création déclenche automatiquement la création ET la migration du
schéma PostgreSQL correspondant -- aucune étape manuelle supplémentaire.

`--create-admin` crée, DANS le schéma de ce tenant (pas dans le schéma
public -- voir README.md pour l'équivalent manuel via `manage.py shell`
que cette option remplace), un utilisateur superutilisateur Django
(is_staff/is_superuser, accès à /admin/) ET applicativement administrateur
(role=RoleUtilisateur.ADMINISTRATEUR, pour les permissions fines
common.permissions.a_role côté API).

`--extra-domain` (répétable) enregistre un domaine SUPPLÉMENTAIRE pour ce
tenant, en plus de <sous-domaine>.MAIN_DOMAIN -- indispensable dès que le
frontend n'est PAS hébergé en sous-domaine du backend (typiquement :
frontend sur Vercel, ex. "civitasnews.vercel.app", backend sur Render,
MAIN_DOMAIN="civitasnews-backend.onrender.com" -- deux domaines sans
relation de sous-domaine entre eux). Voir le correctif correspondant sur
`TenantMiddleware.is_valid_domain` (tenants/middleware.py).

Idempotent : peut être relancée sans effet de bord si le tenant, ses
domaines et/ou son administrateur existent déjà.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Crée un tenant \"établissement\" de développement/démo et son domaine (sous-domaine.MAIN_DOMAIN)."

    def add_arguments(self, parser):
        parser.add_argument("--nom", required=True, help="Nom affiché du tenant (ex: 'Mon Campus').")
        parser.add_argument(
            "--sous-domaine",
            required=True,
            help="Sous-domaine ET nom de schéma PostgreSQL (ex: 'moncampus' -> moncampus.localhost, schéma 'moncampus'). "
                 "Minuscules, chiffres et tirets uniquement -- doit être un identifiant PostgreSQL valide.",
        )
        parser.add_argument("--description", default="")
        parser.add_argument(
            "--extra-domain",
            action="append",
            default=[],
            dest="extra_domains",
            help="Domaine complet supplémentaire à rattacher à ce tenant (ex: civitasnews.vercel.app). "
                 "Répétable : --extra-domain a.example --extra-domain b.example.",
        )
        parser.add_argument(
            "--create-admin",
            action="store_true",
            help="Créer également un administrateur pour CE tenant (schéma du tenant, pas le schéma public).",
        )
        parser.add_argument("--admin-username", default="admin")
        parser.add_argument("--admin-email", default="admin@example.com")
        parser.add_argument(
            "--admin-password",
            default=None,
            help="Requis si --create-admin est utilisé.",
        )

    def handle(self, *args, **options):
        from tenants.models import Tenant
        from domain.models import Domain

        nom = options["nom"]
        sous_domaine = options["sous_domaine"].strip().lower()
        main_domain = settings.MAIN_DOMAIN
        if not main_domain:
            raise CommandError("settings.MAIN_DOMAIN n'est pas configuré.")
        if not sous_domaine.replace('-', '').replace('_', '').isalnum():
            raise CommandError(
                f"'{sous_domaine}' n'est pas un identifiant valide (lettres/chiffres/tirets uniquement)."
            )
        if sous_domaine == 'public':
            raise CommandError("'public' est réservé au tenant plateforme (voir bootstrap_public).")
        if options["create_admin"] and not options["admin_password"]:
            raise CommandError("--admin-password est requis avec --create-admin.")

        full_domain = f"{sous_domaine}.{main_domain}"
        extra_domains = [d.strip().lower() for d in options["extra_domains"] if d.strip()]

        with transaction.atomic():
            tenant, created = Tenant.objects.get_or_create(
                schema_name=sous_domaine,
                defaults={
                    "name": nom,
                    "sous_domaine": sous_domaine,
                    "is_active": True,
                    "description": options["description"],
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Tenant '{nom}' créé (schema_name='{sous_domaine}'). "
                    f"Le schéma PostgreSQL correspondant a été créé et migré automatiquement."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"ℹ️ Tenant '{sous_domaine}' déjà présent (id={tenant.id})."
                ))

            domain, domain_created = Domain.objects.get_or_create(
                domain=full_domain,
                defaults={"tenant": tenant, "is_primary": True},
            )
            if domain_created:
                self.stdout.write(self.style.SUCCESS(f"✅ Domaine '{full_domain}' rattaché au tenant."))
            elif domain.tenant_id != tenant.id:
                raise CommandError(
                    f"Le domaine '{full_domain}' existe déjà et pointe vers un autre tenant "
                    f"(id={domain.tenant_id}). Corrigez manuellement."
                )
            else:
                self.stdout.write(self.style.WARNING(f"ℹ️ Domaine '{full_domain}' déjà rattaché à ce tenant."))

            for extra in extra_domains:
                extra_domain_obj, extra_created = Domain.objects.get_or_create(
                    domain=extra,
                    defaults={"tenant": tenant, "is_primary": False},
                )
                if extra_created:
                    self.stdout.write(self.style.SUCCESS(f"✅ Domaine supplémentaire '{extra}' rattaché au tenant."))
                elif extra_domain_obj.tenant_id != tenant.id:
                    raise CommandError(
                        f"Le domaine '{extra}' existe déjà et pointe vers un autre tenant "
                        f"(id={extra_domain_obj.tenant_id}). Corrigez manuellement."
                    )
                else:
                    self.stdout.write(self.style.WARNING(f"ℹ️ Domaine '{extra}' déjà rattaché à ce tenant."))

        if options["create_admin"]:
            self._create_admin(
                schema_name=tenant.schema_name,
                username=options["admin_username"],
                email=options["admin_email"],
                password=options["admin_password"],
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nTenant prêt.\n"
            f"En local (DNS wildcard *.{main_domain} -> 127.0.0.1) : {full_domain}\n"
            f"En production (Render/Vercel ou toute config sans certificat TLS pour les "
            f"sous-domaines) : appelez le domaine PRINCIPAL du backend et ajoutez l'en-tête "
            f"'X-Tenant-Domain: {full_domain}' à chaque requête (posé automatiquement par le "
            f"frontend, voir src/config/tenantHost.ts) -- voir "
            f"TenantMiddleware.is_valid_domain / _resolve_tenant_dual pour le détail."
        ))

    def _create_admin(self, schema_name, username, email, password):
        from django.contrib.auth import get_user_model
        from django_tenants.utils import schema_context
        from users.models import RoleUtilisateur

        User = get_user_model()

        with schema_context(schema_name):
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(
                    f"ℹ️ Un utilisateur '{username}' existe déjà sur le schéma '{schema_name}'."
                ))
                return

            User.objects.create_superuser(
                username=username, email=email, password=password,
                role=RoleUtilisateur.ADMINISTRATEUR,
            )
            self.stdout.write(self.style.SUCCESS(
                f"✅ Administrateur '{username}' créé sur le tenant '{schema_name}' "
                f"(superutilisateur Django + role='{RoleUtilisateur.ADMINISTRATEUR}')."
            ))
