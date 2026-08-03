from tenants.models import Tenant
from django.utils import timezone
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db import transaction
from config.fonction import formatReponse
from domain.api.v1.services import DomainService
from rest_framework import status


User = get_user_model()

class TenantService:
    """
    Service utilitaire pour la gestion des tenants.
    """
    @staticmethod
    def create_tenant(name, sous_domaine, schema_name, **extra_fields):
        """Crée un nouveau tenant actif."""
        tenant = Tenant.objects.create(
            name=name,
            sous_domaine=sous_domaine,
            schema_name=schema_name,
            is_active=True,
            created_at=timezone.now(),
            updated_at=timezone.now(),
            **extra_fields
        )
        return tenant

    @staticmethod
    def get_tenant_by_id(tenant_id):
        return Tenant.objects.filter(id=tenant_id).first()

    @staticmethod
    def get_tenant_by_sous_domaine(sous_domaine):
        return Tenant.objects.filter(sous_domaine=sous_domaine).first()
    
    @staticmethod
    def get_tenant_by_sous_domaine_actif(request):
        sous_domaine = DomainService.get_sous_domaine_by_request(request)
        formatReponse['type'] = 'error'
        formatReponse['titre'] = 'Informations Erronees'
        formatReponse['niveau'] = 100
        formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)
        formatReponse['message'] = "Le tenant n'existe pas en base de donnees"
        tenant = None
        try:
            tenant = Tenant.objects.filter(sous_domaine=sous_domaine).first()
        except Tenant.DoesNotExist:
            formatReponse['message'] = "Le tenant n'existe pas en base de donnees"
        return tenant, formatReponse
    

    @staticmethod
    def get_tenant_by_schema(schema_name):
        return Tenant.objects.filter(schema_name=schema_name).first()

    @staticmethod
    def list_active_tenants():
        return Tenant.objects.filter(is_active=True)

    @staticmethod
    def list_all_tenants():
        return Tenant.objects.all()

    @staticmethod
    def activate_tenant(tenant_id):
        tenant = TenantService.get_tenant_by_id(tenant_id)
        if tenant and not tenant.is_active:
            tenant.is_active = True
            tenant.updated_at = timezone.now()
            tenant.save(update_fields=['is_active', 'updated_at'])
        return tenant

    @staticmethod
    def deactivate_tenant(tenant_id):
        tenant = TenantService.get_tenant_by_id(tenant_id)
        if tenant and tenant.is_active:
            tenant.is_active = False
            tenant.updated_at = timezone.now()
            tenant.save(update_fields=['is_active', 'updated_at'])
        return tenant

    @staticmethod
    def update_tenant(tenant_id, **fields):
        tenant = TenantService.get_tenant_by_id(tenant_id)
        if tenant:
            for key, value in fields.items():
                setattr(tenant, key, value)
            tenant.updated_at = timezone.now()
            tenant.save()
        return tenant
    
    @staticmethod
    def update_all_tenant_by_perform(data_get, data_update):
        return TenantService.objects.filter(**data_get).all().update(**data_update)

    @staticmethod
    def delete_tenant(tenant_id):
        tenant = TenantService.get_tenant_by_id(tenant_id)
        if tenant:
            tenant.delete()
            return True
        return False

    @staticmethod
    def exists_by_sous_domaine(sous_domaine):
        return Tenant.objects.filter(sous_domaine=sous_domaine).exists()

    @staticmethod
    def exists_by_schema(schema_name):
        return Tenant.objects.filter(schema_name=schema_name).exists()

    @staticmethod
    def exists_by_id(tenant_id):
        return Tenant.objects.filter(id=tenant_id).exists()

    @staticmethod
    @transaction.atomic
    def bulk_deactivate_tenants(tenant_ids):
        return Tenant.objects.filter(id__in=tenant_ids, is_active=True).update(is_active=False, updated_at=timezone.now())

    @staticmethod
    @transaction.atomic
    def bulk_activate_tenants(tenant_ids):
        return Tenant.objects.filter(id__in=tenant_ids, is_active=False).update(is_active=True, updated_at=timezone.now()) 