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

Avec auto_create_schema=True sur le modèle Tenant (voir tenants/models.py),
la création déclenche automatiquement la création ET la migration du
schéma PostgreSQL correspondant -- aucune étape manuelle supplémentaire.

Idempotent : peut être relancée sans effet de bord si le tenant et son
domaine existent déjà.
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

        full_domain = f"{sous_domaine}.{main_domain}"

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

        self.stdout.write(self.style.SUCCESS(
            f"\nTenant prêt. Pointez vos requêtes API (et le VITE_API_BASE_URL du frontend) vers :\n"
            f"  http://{full_domain}:8000/api\n"
            f"(ajoutez '127.0.0.1 {full_domain}' à /etc/hosts si vous n'utilisez pas déjà un DNS wildcard "
            f"*.{main_domain} -> 127.0.0.1)."
        ))
