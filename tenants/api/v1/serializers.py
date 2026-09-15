import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _
from tenants.models import (
    Tenant,
    TenantInformationsPrimaires,
    TenantDocumentRequis,
    TenantDocumentGenerique,
    ContraintesDocumentRequis,
    TypeDocumentRequis,
    PeriodiciteDocument,
    valider_fichier_selon_contraintes,
)
from domain.api.v1.serializers import DomainSerializer
from .services import TenantService
from users.api.v1.services import normaliser_identifiant, is_email, is_telephone_valide


User = get_user_model()


class TenantCreateSerializer(serializers.Serializer):
    """
    Création self-service d'un tenant + de son premier administrateur
    (architecture tenant-autonome -- voir Tenant.create_with_domain,
    tenants/models.py). `identifiant`/`password` suivent EXACTEMENT le
    même contrat que l'inscription self-service classique
    (IdentifiantRegisterSerializer, users/api/v1/serializers.py) : un
    seul champ identifiant (email OU téléphone, détecté automatiquement),
    pour que le formulaire de création de tenant puisse réutiliser les
    mêmes composants/validations côté frontend que n'importe quel autre
    formulaire d'inscription.
    """
    name = serializers.CharField(max_length=100, required=True)
    sous_domaine = serializers.CharField(max_length=50, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    identifiant = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True, validators=[validate_password])

    def validate_sous_domaine(self, value):
        value = value.strip().lower()
        if not re.match(r'^[a-z0-9-]+$', value):
            raise serializers.ValidationError(
                "Le sous-domaine ne peut contenir que des lettres minuscules, des chiffres et des tirets."
            )
        if len(value) < 3:
            raise serializers.ValidationError("Le sous-domaine doit contenir au moins 3 caractères.")
        if TenantService.exists_by_sous_domaine(value):
            raise serializers.ValidationError("Ce sous-domaine est déjà pris.")
        return value

    def validate_identifiant(self, value):
        value = normaliser_identifiant(value)
        if not value or not (is_email(value) or is_telephone_valide(value)):
            raise serializers.ValidationError(
                "Entrez un email valide ou un numéro de téléphone valide (9 à 15 chiffres) pour l'administrateur."
            )
        return value


class TenantSerializer(serializers.ModelSerializer):
    """Vue complète (usage interne/admin) -- inclut schema_name/settings, jamais exposés publiquement."""
    # domains = DomainSerializer(many=True, read_only=True)
    logo = serializers.CharField(required=False, allow_null=True)
    class Meta:
        model = Tenant
        fields = ['logo', 'id', 'name', 'sous_domaine', 'schema_name', 'is_active', 'is_public', 'created_at', 'updated_at', 'description', 'settings']
        read_only_fields = ('schema_name',)


class TenantPublicSerializer(serializers.ModelSerializer):
    """
    Vue PUBLIQUE (annuaire, GET /tenants/v1/ ; GET /tenants/v1/publics/ ;
    réponse de POST /tenants/v1/) -- délibérément dépourvue de
    schema_name/settings/updated_at : détails internes sans valeur pour
    un visiteur, voir OrganisationsSection.tsx côté civitas-news qui
    affiche cette liste comme "Organisations" de la page d'accueil.

    `is_public` et `domain` sont exposés (contrairement au reste des
    champs internes ci-dessus) car le frontend en a explicitement besoin
    pour la réforme multi-tenant des requêtes GET : `domain` est la
    valeur EXACTE à ajouter à l'en-tête X-Tenant-Domain pour ce tenant
    (voir config/fonction.py:get_tenant_header_hostnames côté backend),
    `is_public` permet au frontend de filtrer/afficher sans avoir à
    deviner la règle à partir d'autre chose.
    """
    logo = serializers.CharField(required=False, allow_null=True)
    domain = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ['id', 'name', 'sous_domaine', 'domain', 'logo', 'description', 'is_public', 'created_at']
        read_only_fields = fields

    def get_domain(self, tenant):
        from domain.models import Domain
        primaire = Domain.get_primary_domain(tenant)
        return primaire.domain if primaire else None


def _valider_periode(valide_du, valide_au):
    """Même règle que `common.models.PeriodeValiditeMixin.clean()` --
    répétée ici côté serializer pour renvoyer une erreur 400 propre
    plutôt qu'une exception au `save()` (voir la convention déjà en
    place : `users`/`sondages` valident aussi dans leurs serializers
    plutôt que de compter sur `full_clean()`, jamais appelé
    automatiquement par DRF)."""
    if valide_du and valide_au and valide_du > valide_au:
        raise serializers.ValidationError({
            'valide_au': _('La date de fin de validité doit être postérieure à la date de début.'),
        })


class TenantInformationsPrimairesSerializer(serializers.ModelSerializer):
    """
    Fiche d'identité primaire d'un tenant — voir
    `tenants.models.TenantInformationsPrimaires`. `tenant` et les champs
    de vérification plateforme (`statut`, `verifie_par`, `verifie_le`,
    `commentaire_verification`) sont en lecture seule ici : cette fiche
    est résolue et rattachée automatiquement au tenant COURANT côté vue
    (voir `TenantInformationsPrimairesAPIView`, tenants/api/v1/views.py),
    jamais choisie par le client, et la vérification est un geste de
    PLATEFORME (admin global), pas du ressort de ce endpoint self-service.
    """
    id = serializers.CharField(source='pk', read_only=True)
    tenant = serializers.CharField(source='tenant_id', read_only=True)
    pourcentage_completion = serializers.ReadOnlyField()

    class Meta:
        model = TenantInformationsPrimaires
        fields = [
            'id', 'tenant', 'statut', 'pourcentage_completion',
            'forme_juridique', 'secteur_activite', 'raison_sociale', 'sigle',
            'numero_rccm', 'numero_nif', 'numero_agrement', 'date_creation_ou_agrement',
            'adresse_siege', 'ville', 'province', 'pays',
            'telephone_principal', 'telephone_secondaire', 'email_contact', 'site_web', 'reseaux_sociaux',
            'responsable_nom_complet', 'responsable_fonction', 'responsable_telephone', 'responsable_email',
            'contact_operationnel_nom', 'contact_operationnel_fonction',
            'contact_operationnel_telephone', 'contact_operationnel_email',
            'effectif_estime', 'zone_couverture', 'description_activites',
            'commentaire_verification', 'verifie_le',
            'cree_le', 'modifie_le',
        ]
        read_only_fields = [
            'id', 'tenant', 'statut', 'pourcentage_completion',
            'commentaire_verification', 'verifie_le', 'cree_le', 'modifie_le',
        ]


class TenantDocumentRequisSerializer(serializers.ModelSerializer):
    """
    Soumission d'un document du catalogue FIXE — voir
    `tenants.models.TenantDocumentRequis`/`TypeDocumentRequis`. Expose
    `contraintes` (calculées depuis `ContraintesDocumentRequis`, jamais
    stockées) pour que le frontend affiche/valide les restrictions
    (taille, formats, périodicité) sans les dupliquer en dur de son côté.
    Le contrôle plateforme (`statut`, `motif_rejet`, `verifie_par`,
    `verifie_le`) reste en lecture seule ici : traité depuis l'admin
    global, pas via ce endpoint self-service tenant.
    """
    id = serializers.CharField(source='pk', read_only=True)
    tenant = serializers.CharField(source='tenant_id', read_only=True)
    type_affiche = serializers.CharField(source='get_type_display', read_only=True)
    statut_affiche = serializers.CharField(source='get_statut_display', read_only=True)
    contraintes = serializers.SerializerMethodField()
    fichier_url = serializers.SerializerMethodField()

    class Meta:
        model = TenantDocumentRequis
        fields = [
            'id', 'tenant', 'type', 'type_affiche', 'statut', 'statut_affiche', 'contraintes',
            'fichier', 'fichier_url', 'nom_fichier_original', 'taille', 'type_mime',
            'valide_du', 'valide_au', 'commentaire_soumission', 'motif_rejet',
            'cree_le', 'modifie_le',
        ]
        read_only_fields = [
            'id', 'tenant', 'type_affiche', 'statut', 'statut_affiche', 'contraintes',
            'fichier_url', 'nom_fichier_original', 'taille', 'type_mime', 'motif_rejet',
            'cree_le', 'modifie_le',
        ]
        extra_kwargs = {'fichier': {'write_only': True}}

    def get_contraintes(self, obj):
        contraintes = ContraintesDocumentRequis.pour(obj.type)
        periodicite = contraintes.get('periodicite', PeriodiciteDocument.PERMANENT)
        return {
            'extensions_autorisees': contraintes.get('extensions_autorisees', []),
            'taille_max_mo': contraintes.get('taille_max_mo'),
            'periodicite': periodicite.value,
        }

    def get_fichier_url(self, obj):
        if not obj.fichier:
            return None
        request = self.context.get('request')
        try:
            url = obj.fichier.url
        except ValueError:
            return None
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        type_document = attrs.get('type', getattr(self.instance, 'type', None))
        valide_du = attrs.get('valide_du', getattr(self.instance, 'valide_du', None))
        valide_au = attrs.get('valide_au', getattr(self.instance, 'valide_au', None))
        _valider_periode(valide_du, valide_au)
        contraintes = ContraintesDocumentRequis.pour(type_document)
        if contraintes.get('periodicite') != PeriodiciteDocument.PERMANENT and not valide_du:
            raise serializers.ValidationError({
                'valide_du': _('Ce type de document est périodique : la période couverte (Valide du) est obligatoire.'),
            })
        fichier = attrs.get('fichier')
        if fichier:
            try:
                valider_fichier_selon_contraintes(fichier, contraintes)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'fichier': exc.messages})
        return attrs


class TenantDocumentGeneriqueSerializer(serializers.ModelSerializer):
    """
    Dépôt libre — voir `tenants.models.TenantDocumentGenerique`. Pas de
    catalogue fixe : `type_libre` est un texte libre indiqué par le
    tenant, uniquement utile au tri/à la recherche.
    """
    id = serializers.CharField(source='pk', read_only=True)
    tenant = serializers.CharField(source='tenant_id', read_only=True)
    statut_affiche = serializers.CharField(source='get_statut_display', read_only=True)
    fichier_url = serializers.SerializerMethodField()

    class Meta:
        model = TenantDocumentGenerique
        fields = [
            'id', 'tenant', 'nom', 'type_libre', 'description', 'statut', 'statut_affiche',
            'fichier', 'fichier_url', 'nom_fichier_original', 'taille', 'type_mime',
            'valide_du', 'valide_au', 'cree_le', 'modifie_le',
        ]
        read_only_fields = [
            'id', 'tenant', 'statut', 'statut_affiche', 'fichier_url',
            'nom_fichier_original', 'taille', 'type_mime', 'cree_le', 'modifie_le',
        ]
        extra_kwargs = {'fichier': {'write_only': True}}

    def get_fichier_url(self, obj):
        if not obj.fichier:
            return None
        request = self.context.get('request')
        try:
            url = obj.fichier.url
        except ValueError:
            return None
        return request.build_absolute_uri(url) if request else url

    def validate(self, attrs):
        valide_du = attrs.get('valide_du', getattr(self.instance, 'valide_du', None))
        valide_au = attrs.get('valide_au', getattr(self.instance, 'valide_au', None))
        _valider_periode(valide_du, valide_au)
        fichier = attrs.get('fichier')
        if fichier:
            try:
                valider_fichier_selon_contraintes(fichier, TenantDocumentGenerique.CONTRAINTES_GENERIQUES)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'fichier': exc.messages})
        return attrs


class TypeDocumentRequisCatalogueSerializer(serializers.Serializer):
    """
    Représente UNE entrée du catalogue fixe (`TypeDocumentRequis`) pour
    `GET /tenants/v1/catalogue-documents-requis/` — pas un ModelSerializer :
    il n'y a pas de ligne en base, uniquement du code (voir
    `TenantDossierService.construire_catalogue`, tenants/api/v1/services.py).
    """
    type = serializers.CharField()
    libelle = serializers.CharField()
    extensions_autorisees = serializers.ListField(child=serializers.CharField())
    taille_max_mo = serializers.IntegerField(allow_null=True)
    periodicite = serializers.CharField()
    periodicite_libelle = serializers.CharField()
