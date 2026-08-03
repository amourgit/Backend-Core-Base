from rest_framework import serializers
from django.contrib.auth import get_user_model
from tenants.models import Tenant
from domain.api.v1.serializers import DomainSerializer


User = get_user_model()


class TenantCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=True)
    sous_domaine = serializers.CharField(max_length=50, required=True)
    admin_email = serializers.EmailField(required=True)
    admin_password = serializers.CharField(max_length=128, required=False, allow_null=True)
    admin_username = serializers.CharField(max_length=150, required=False, allow_null=True)


class TenantSerializer(serializers.ModelSerializer):
    # domains = DomainSerializer(many=True, read_only=True)
    logo = serializers.CharField(required=False, allow_null=True)
    class Meta:
        model = Tenant
        fields = ['logo', 'id', 'name', 'sous_domaine', 'schema_name', 'is_active', 'created_at', 'updated_at', 'description', 'settings']
        read_only_fields = ('schema_name',)
