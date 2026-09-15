from tenants.models import (
    Tenant,
    TenantInformationsPrimaires,
    TenantDocumentRequis,
    TenantDocumentGenerique,
    TypeDocumentRequis,
    ContraintesDocumentRequis,
    PeriodiciteDocument,
    TenantTutelle,
    StatutTutelle,
)
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
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


class TenantDossierService:
    """
    Service pour la fiche d'identité, les documents requis (catalogue
    fixe) et les documents génériques d'un tenant — voir la note
    d'architecture en tête de `tenants/models.py`.
    """

    @staticmethod
    def get_or_create_informations(tenant):
        """Fiche d'identité — une par tenant, créée à la volée au premier
        accès plutôt que par signal (voir docstring de
        `TenantInformationsPrimaires`)."""
        informations, _cree = TenantInformationsPrimaires.objects.get_or_create(tenant=tenant)
        return informations

    @staticmethod
    def construire_catalogue():
        """Catalogue fixe des documents requis (`TypeDocumentRequis`),
        avec leurs contraintes — ne touche PAS la base de données,
        entièrement dérivé du code (voir `ContraintesDocumentRequis`).
        Utilisé par `GET /tenants/v1/catalogue-documents-requis/`
        (accessible publiquement, voir la vue) et par
        `construire_dossier` ci-dessous."""
        catalogue = []
        for type_document in TypeDocumentRequis:
            contraintes = ContraintesDocumentRequis.pour(type_document)
            periodicite = contraintes.get('periodicite', PeriodiciteDocument.PERMANENT)
            catalogue.append({
                'type': type_document.value,
                'libelle': str(type_document.label),
                'extensions_autorisees': contraintes.get('extensions_autorisees', []),
                'taille_max_mo': contraintes.get('taille_max_mo'),
                'periodicite': periodicite.value,
                'periodicite_libelle': str(periodicite.label),
            })
        return catalogue

    @staticmethod
    def construire_checklist_documents_requis(tenant):
        """Pour chaque type du catalogue fixe, la ou les soumissions déjà
        faites par ce tenant (triées de la plus récente à la plus
        ancienne) -- une checklist "ce qui est fourni / ce qui manque",
        utile à la plateforme ET au tenant lui-même (voir
        `TenantDossierAPIView`)."""
        soumissions_par_type = {}
        for soumission in TenantDocumentRequis.objects.filter(tenant=tenant).order_by('-cree_le'):
            soumissions_par_type.setdefault(soumission.type, []).append(soumission)

        checklist = []
        for entree in TenantDossierService.construire_catalogue():
            soumissions = soumissions_par_type.get(entree['type'], [])
            checklist.append({
                **entree,
                'soumissions': soumissions,
                'fourni': bool(soumissions),
            })
        return checklist

    @staticmethod
    def construire_dossier(tenant):
        """Vue d'ensemble complète du dossier d'un tenant : fiche
        d'identité + checklist des documents requis + documents
        génériques -- voir `TenantDossierAPIView`."""
        return {
            'informations': TenantDossierService.get_or_create_informations(tenant),
            'documents_requis': TenantDossierService.construire_checklist_documents_requis(tenant),
            'documents_generiques': TenantDocumentGenerique.objects.filter(tenant=tenant).order_by('-cree_le'),
        }


class TenantTutelleService:
    """
    Service pour la relation de tutelle entre tenants (voir
    `tenants.models.TenantTutelle`) : requêtage courant et
    reconstruction de la hiérarchie ("cascade flexible" — voir la note
    d'architecture en tête de tenants/models.py).
    """

    @staticmethod
    def relations_du_tenant(tenant):
        """Toutes les relations (tous statuts) où `tenant` apparaît,
        quel que soit son rôle (tuteur, sous tutelle ou initiateur)."""
        return TenantTutelle.objects.filter(
            Q(tenant_tutelle=tenant) | Q(tenant_sous_tutelle=tenant)
        ).select_related('tenant_tutelle', 'tenant_sous_tutelle', 'tenant_initiateur')

    @staticmethod
    def en_attente_de_validation_par(tenant):
        """Propositions EN_ATTENTE_VALIDATION dont `tenant` est
        précisément le DESTINATAIRE (celui qui doit agir) -- pas
        seulement lié à la relation (l'initiateur a déjà validé de
        facto en la créant)."""
        candidates = TenantTutelle.objects.filter(
            statut=StatutTutelle.EN_ATTENTE_VALIDATION,
        ).filter(
            Q(tenant_tutelle=tenant) | Q(tenant_sous_tutelle=tenant)
        ).select_related('tenant_tutelle', 'tenant_sous_tutelle', 'tenant_initiateur')
        return [relation for relation in candidates if relation.tenant_destinataire.id == tenant.id]

    @staticmethod
    def chaine_ascendante(tenant, profondeur_max=50):
        """Liste ORDONNÉE des tenants qui exercent une tutelle ACTIVE sur
        `tenant`, du plus proche au plus lointain -- ex: [Université,
        Ministère] pour une École rattachée à cette Université."""
        chaine = []
        courant = tenant
        vus = {tenant.id}
        for _tour in range(profondeur_max):
            relation = TenantTutelle.objects.filter(
                tenant_sous_tutelle=courant, statut=StatutTutelle.ACTIVE,
            ).select_related('tenant_tutelle').first()
            if not relation or relation.tenant_tutelle_id in vus:
                break
            chaine.append(relation.tenant_tutelle)
            vus.add(relation.tenant_tutelle_id)
            courant = relation.tenant_tutelle
        return chaine

    @staticmethod
    def descendants(tenant, profondeur_max=50):
        """Tous les tenants sous la tutelle ACTIVE de `tenant`, directe
        ou indirecte (cascade descendante complète) -- parcours en
        largeur, sans doublon, ordre non garanti au-delà du premier
        niveau."""
        resultat = []
        vus = {tenant.id}
        a_visiter = [tenant.id]
        for _tour in range(profondeur_max):
            if not a_visiter:
                break
            enfants = list(Tenant.objects.filter(
                tutelles_subies__tenant_tutelle_id__in=a_visiter,
                tutelles_subies__statut=StatutTutelle.ACTIVE,
            ).distinct())
            suivant = []
            for enfant in enfants:
                if enfant.id not in vus:
                    vus.add(enfant.id)
                    resultat.append(enfant)
                    suivant.append(enfant.id)
            a_visiter = suivant
        return resultat