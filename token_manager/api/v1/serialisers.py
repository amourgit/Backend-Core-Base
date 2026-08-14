from rest_framework import serializers
from django.contrib.auth import get_user_model
from token_manager.models import TokenSettings, TokenManager
# from tenants.models import Tenant
# from config.fonction import formatReponse
# from rest_framework import status

User = get_user_model()


class TokenObtenSerializer(serializers.Serializer):
    """
    Sérialiseur pour les demandes de tokens -- connexion simplifiée par
    un unique champ `identifiant` (email OU numéro de téléphone, voir
    users/api/v1/services.py:get_user_by_identifiant), plutôt qu'un
    `username` que l'utilisateur ne choisit ni ne connaît (généré
    automatiquement à l'inscription, voir
    generer_username_depuis_identifiant).
    """
    identifiant = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, data):
        """
        Validation des données de la demande de token
        """
        return data

class TokenRefreshSerializer(serializers.Serializer):
    """
    Sérialiseur pour les demandes de refresh de token
    """
    refresh = serializers.CharField(required=True)
    def validate(self, data):
        """
        Validation des données de la demande de refresh de token
        """
        return data


class TokenResponseSerializer(serializers.Serializer):
    """
    Sérialiseur pour les réponses de tokens
    """
    access = serializers.CharField()
    refresh = serializers.CharField()
    tenant_schema = serializers.CharField()
    expires_in = serializers.IntegerField()


class TokenSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenSettings
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        """
        Validation des paramètres de configuration des tokens
        """
        errors = {}

        # Validation des durées de vie
        if data.get('access_token_lifetime', 0) <= 0:
            errors['access_token_lifetime'] = "La durée de vie doit être positive"
        if data.get('refresh_token_lifetime', 0) <= 0:
            errors['refresh_token_lifetime'] = "La durée de vie doit être positive"
        if data.get('access_token_lifetime', 0) >= data.get('refresh_token_lifetime', 0):
            errors['access_token_lifetime'] = "La durée de vie du token d'accès doit être inférieure à celle du refresh token"

        # Validation des limites
        if data.get('max_tokens_per_user', 0) <= 0:
            errors['max_tokens_per_user'] = "Le nombre maximum de tokens doit être positif"

        # Validation de la blacklist
        if data.get('enable_blacklist', False):
            if data.get('blacklist_cleanup_after', 0) <= 0:
                errors['blacklist_cleanup_after'] = "La durée de conservation doit être positive"

        if errors:
            raise serializers.ValidationError(errors)

        return data


class TokenManagerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenManager
        fields = [
            'id', 'created_at', 'expires_at', 'last_used', 'is_revoked', 'revoked_at',
            'user_id', 'username', 'tenant_id', 'access_token', 'refresh_token',
            'ip_address', 'device_id', 'device_family', 'device_brand', 'device_model',
            'device_type', 'os_family', 'browser_family', 'user_agent', 'location', 'is_current'
        ]
        read_only_fields = [
            'id', 'created_at', 'expires_at', 'last_used', 'is_revoked', 'revoked_at'
        ]


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id'] 