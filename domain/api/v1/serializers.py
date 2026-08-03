from rest_framework import serializers
from django.contrib.auth import get_user_model
from domain.models import Domain


User = get_user_model()

class DomainSerializer(serializers.ModelSerializer):
    tenant_details = serializers.SerializerMethodField()

    class Meta:
        model = Domain
        fields = '__all__'

    def get_tenant_details(self, obj):
        return {
            'id': obj.tenant.id,
            'name': obj.tenant.name,
            'schema_name': obj.tenant.schema_name
        }


