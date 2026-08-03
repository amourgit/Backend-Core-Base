"""
Commande d'amorçage de l'espace ADMIN GLOBAL (schéma public).

django-tenants exige qu'un objet Tenant avec schema_name="public" existe,
et qu'un Domain pointe vers lui, pour que le domaine racine (ex: "localhost")
puisse être résolu par le middleware de tenant. Sans cela, /admin/ sur le
domaine racine renverra systématiquement "Domaine ou tenant introuvable",
même après correction du middleware et des settings.

Usage :
    python manage.py bootstrap_public
    python manage.py bootstrap_public --create-superuser \
        --username admin --email admin@example.com --password "un-mot-de-passe-fort"

Idempotent : peut être relancée sans effet de bord si le tenant public et
son domaine existent déjà.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_tenants.utils import get_public_schema_name


class Command(BaseCommand):
    help = "Crée le tenant public et son domaine, prérequis à l'espace admin global."

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-superuser",
            action="store_true",
            help="Créer également un super-administrateur PLATEFORME (schéma public).",
        )
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@example.com")
        parser.add_argument(
            "--password",
            default=None,
            help="Requis si --create-superuser est utilisé.",
        )

    def handle(self, *args, **options):
        from tenants.models import Tenant
        from domain.models import Domain

        public_schema = get_public_schema_name()  # 'public'
        main_domain = settings.MAIN_DOMAIN
        if not main_domain:
            raise CommandError("settings.MAIN_DOMAIN n'est pas configuré.")

        with transaction.atomic():
            tenant, created = Tenant.objects.get_or_create(
                schema_name=public_schema,
                defaults={
                    "name": "Plateforme EDUNET Gabon",
                    "sous_domaine": public_schema,
                    "is_active": True,
                    "description": "Tenant public : administration globale de la plateforme.",
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Tenant public créé (schema_name='{public_schema}')."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"ℹ️ Tenant public déjà présent (id={tenant.id})."
                ))

            domain, domain_created = Domain.objects.get_or_create(
                domain=main_domain,
                defaults={"tenant": tenant, "is_primary": True},
            )
            if domain_created:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Domaine '{main_domain}' rattaché au tenant public."
                ))
            elif domain.tenant_id != tenant.id:
                raise CommandError(
                    f"Le domaine '{main_domain}' existe déjà et pointe vers un "
                    f"autre tenant (id={domain.tenant_id}). Corrigez manuellement."
                )
            else:
                self.stdout.write(self.style.WARNING(
                    f"ℹ️ Domaine '{main_domain}' déjà rattaché au tenant public."
                ))

        if options["create_superuser"]:
            self._create_superuser(
                username=options["username"],
                email=options["email"],
                password=options["password"],
            )

        self.stdout.write(self.style.SUCCESS(
            "\nEspace admin global prêt. Connectez-vous sur : "
            f"http://{main_domain}:8000/admin/"
        ))

    def _create_superuser(self, username, email, password):
        from django.contrib.auth import get_user_model
        from django_tenants.utils import schema_context

        if not password:
            raise CommandError(
                "--password est requis avec --create-superuser."
            )

        User = get_user_model()
        public_schema = get_public_schema_name()

        with schema_context(public_schema):
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(
                    f"ℹ️ Un utilisateur '{username}' existe déjà sur le schéma public."
                ))
                return

            User.objects.create_superuser(
                username=username, email=email, password=password
            )
            self.stdout.write(self.style.SUCCESS(
                f"✅ Super-administrateur PLATEFORME '{username}' créé sur le schéma public."
            ))
