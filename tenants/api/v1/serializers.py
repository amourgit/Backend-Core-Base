import re
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from tenants.models import Tenant
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
        fields = ['logo', 'id', 'name', 'sous_domaine', 'schema_name', 'is_active', 'created_at', 'updated_at', 'description', 'settings']
        read_only_fields = ('schema_name',)


class TenantPublicSerializer(serializers.ModelSerializer):
    """
    Vue PUBLIQUE (annuaire, GET /tenants/v1/ ; réponse de POST
    /tenants/v1/) -- délibérément dépourvue de schema_name/settings/
    is_active/updated_at : détails internes sans valeur pour un visiteur,
    voir OrganisationsSection.tsx côté civitas-news qui affiche cette
    liste comme "Organisations" de la page d'accueil.
    """
    logo = serializers.CharField(required=False, allow_null=True)
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'sous_domaine', 'logo', 'description', 'created_at']
        read_only_fields = fields
