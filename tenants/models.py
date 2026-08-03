from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django_tenants.models import TenantMixin
from django.utils.text import slugify
from django.db import connection
from django.db import transaction
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.management import call_command
from django_tenants.utils import schema_context
import re
import secrets
import string
from django.apps import apps
from django.db.migrations.loader import MigrationLoader

User = get_user_model()

class Tenant(TenantMixin):
    """
    Modèle représentant un tenant dans le système multi-tenant.
    Chaque tenant a son propre schéma de base de données.
    """
    auto_create_schema = True
    auto_drop_schema = True
    
    name = models.CharField(_('Nom'), max_length=100)
    sous_domaine = models.CharField(_('Sous-domaine'), max_length=100, unique=True)
    schema_name = models.CharField(_('Nom du schéma'), max_length=63, unique=True)
    is_active = models.BooleanField(_('Actif'), default=True)
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Mis à jour le'), auto_now=True)
    description = models.TextField(_('Description'), blank=True)
    logo = models.ImageField(_('Logo'), upload_to='tenant_logos/', null=True, blank=True)
    settings = models.JSONField(_('Paramètres'), default=dict, blank=True)

    class Meta:
        verbose_name = _('Tenant')
        verbose_name_plural = _('Tenants')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.sous_domaine})"

    def save(self, *args, **kwargs):
        """Surcharge de save() pour automatiser certaines opérations."""
        if not self.schema_name:
            self.schema_name = slugify(self.sous_domaine).replace('-', '_')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Surcharge de delete() pour nettoyer le schéma."""
        try:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{self.schema_name}" CASCADE')
        except Exception as e:
            print(f"⚠️ Erreur suppression schéma {self.schema_name}: {str(e)}")
        super().delete(*args, **kwargs)

    def clean(self):
        """Validation des données avant sauvegarde."""
        super().clean()
        
        if self.sous_domaine:
            if not re.match(r'^[a-z0-9-]+$', self.sous_domaine):
                raise ValidationError(
                    _('Le sous-domaine ne peut contenir que des lettres minuscules, des chiffres et des tirets')
                )
                
            if len(self.sous_domaine) < 3:
                raise ValidationError(
                    _('Le sous-domaine doit contenir au moins 3 caractères')
                )

    @property
    def is_accessible(self):
        """Vérifie si le tenant est accessible."""
        return self.is_active and self.schema_name

    @classmethod
    def create_with_domain(cls, name: str, sous_domaine: str, admin_email: str, admin_password: str = None, admin_username: str = None, **kwargs):
        """
        Factory method pour créer un tenant avec son domaine et un superuser.
        """
        from domain.models import Domain
        import secrets
        import string
        
        try:
            # 1. Validation des paramètres
            if not name or not sous_domaine or not admin_email:
                raise ValidationError("Nom, sous-domaine et email administrateur requis")
            
            if not settings.MAIN_DOMAIN:
                raise ValidationError("MAIN_DOMAIN non configuré dans les paramètres")
            
            if not admin_username:
                raise ValidationError("Le nom d'utilisateur administrateur est requis")
            if not admin_email:
                raise ValidationError("L'email administrateur est requis")
            
            # 2. Préparation des données
            schema_name = slugify(sous_domaine).replace('-', '_')
            domain_name = f"{sous_domaine}.{settings.MAIN_DOMAIN}"
            
            # 3. Vérification des doublons
            if cls.objects.filter(sous_domaine=sous_domaine).exists():
                raise ValidationError(f"Le sous-domaine '{sous_domaine}' existe déjà")
                
            if cls.objects.filter(schema_name=schema_name).exists():
                raise ValidationError(f"Le schéma '{schema_name}' existe déjà")
                
            if Domain.objects.filter(domain=domain_name).exists():
                raise ValidationError(f"Le domaine '{domain_name}' existe déjà")
            
            # 4. Création atomique du tenant et du domaine
            with transaction.atomic():
                # Création du tenant
                tenant = cls(
                    name=name,
                    sous_domaine=sous_domaine,
                    schema_name=schema_name,
                    **kwargs
                )
                tenant.full_clean()
                tenant.save()
                
                # Création du domaine
                domain = Domain.objects.create(
                    tenant=tenant,
                    domain=domain_name,
                    is_primary=True
                )
                
                # 5. Création du schéma s'il n'existe pas
                try:
                    print(f"🔄 Création du schéma {schema_name}")
                    with connection.cursor() as cursor:
                        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";')
                    print(f"✅ Schéma {schema_name} créé avec succès")
                except Exception as e:
                    print(f"❌ Erreur lors de la création du schéma: {str(e)}")
                    raise ValidationError(f"Erreur lors de la création du schéma: {str(e)}")
                
                # 6. Application des migrations si le tenant est actif
                if tenant.is_active:
                    try:
                        print(f"🔄 Application des migrations pour le schéma {schema_name}")
                        
                        # Appliquer les migrations de base d'abord
                        print("📦 Application des migrations de base...")
                        call_command('migrate', '--noinput', schema=schema_name)
                        
                        print(f"✅ Migrations appliquées avec succès pour {schema_name}")
                    except Exception as e:
                        print(f"❌ Erreur lors de l'application des migrations: {str(e)}")
                        raise ValidationError(f"Erreur lors de l'application des migrations: {str(e)}")
                
                # 7. Création du superuser dans le schéma du tenant
                admin_credentials = {}
                with schema_context(schema_name):
                    # Génération du mot de passe si non fourni
                    if not admin_password:
                        admin_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
                    
                    # Création du superuser
                    try:
                        print(f"👤 Création du superuser pour {schema_name}")
                        admin = User.objects.create_superuser(
                            username=admin_username,
                            email=admin_email,
                            password=admin_password
                        )
                        admin_credentials = {
                            'email': admin_email,
                            'password': admin_password
                        }
                        print(f"✅ Superuser créé avec succès pour {schema_name}")
                    except Exception as e:
                        print(f"❌ Erreur lors de la création du superuser: {str(e)}")
                        raise ValidationError(f"Erreur lors de la création du superuser: {str(e)}")
                
                return tenant, domain, admin_credentials
                
        except Exception as e:
            # En cas d'erreur, on nettoie le schéma si créé
            if 'tenant' in locals() and hasattr(tenant, 'schema_name'):
                try:
                    print(f"🧹 Nettoyage du schéma {tenant.schema_name} suite à une erreur")
                    with connection.cursor() as cursor:
                        cursor.execute(f'DROP SCHEMA IF EXISTS "{tenant.schema_name}" CASCADE;')
                except Exception as cleanup_error:
                    print(f"⚠️ Erreur lors du nettoyage du schéma: {str(cleanup_error)}")
            raise ValidationError(str(e))


class TenantAwareModel(models.Model):
    """
    Classe de base pour les modèles qui doivent être conscients du tenant.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        abstract = True


