from rest_framework import serializers

from news.models import News
from ... import models


class LienScopeSerializer(serializers.Serializer):
    etablissement = serializers.CharField(required=False, allow_blank=True)
    province = serializers.CharField(required=False, allow_blank=True)
    promotion = serializers.CharField(required=False, allow_blank=True)
    organisation = serializers.CharField(required=False, allow_blank=True)
    classe = serializers.CharField(required=False, allow_blank=True)


class LienPublicationSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    news_id = serializers.CharField(read_only=True)
    sujet_id = serializers.CharField(source='news_id', read_only=True)
    url_publique = serializers.CharField(read_only=True)
    url_courte = serializers.SerializerMethodField()
    qr_code = serializers.SerializerMethodField()
    mot_de_passe = serializers.BooleanField(source='a_mot_de_passe', read_only=True)
    scope = serializers.SerializerMethodField()
    clics = serializers.SerializerMethodField()
    scans = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)

    class Meta:
        model = models.LienPublication
        fields = (
            'id', 'news_id', 'sujet_id', 'url_publique', 'url_courte', 'qr_code', 'visibilite',
            'mot_de_passe', 'expiration', 'usage_unique', 'scope', 'clics', 'scans', 'created_at',
        )

    def get_url_courte(self, obj):
        from django.conf import settings
        base = getattr(settings, 'FRONTEND_BASE_URL', '').rstrip('/')
        return f'{base}/l/{obj.code_court}'

    def get_qr_code(self, obj):
        if not obj.qr_code:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.qr_code.url) if request else obj.qr_code.url

    def get_scope(self, obj):
        scope = {
            'etablissement': obj.scope_etablissement,
            'province': obj.scope_province,
            'promotion': obj.scope_promotion,
            'organisation': obj.scope_organisation,
            'classe': obj.scope_classe,
        }
        return scope if any(scope.values()) else None

    def get_clics(self, obj):
        return obj.acces.filter(type_acces=models.LienAcces.TypeAcces.CLIC).count()

    def get_scans(self, obj):
        return obj.acces.filter(type_acces=models.LienAcces.TypeAcces.SCAN).count()


class LienPublicationEcritureSerializer(serializers.ModelSerializer):
    news = serializers.PrimaryKeyRelatedField(queryset=News.objects.all())
    url_publique = serializers.URLField(required=False, allow_blank=True)
    mot_de_passe = serializers.CharField(required=False, allow_blank=True, write_only=True)
    scope = LienScopeSerializer(required=False)

    class Meta:
        model = models.LienPublication
        fields = ('news', 'url_publique', 'visibilite', 'mot_de_passe', 'expiration', 'usage_unique', 'scope')

    def create(self, validated_data):
        from django.conf import settings
        from django.contrib.auth.hashers import make_password

        scope = validated_data.pop('scope', {}) or {}
        mot_de_passe = validated_data.pop('mot_de_passe', '')
        news = validated_data['news']

        if not validated_data.get('url_publique'):
            base = getattr(settings, 'FRONTEND_BASE_URL', '').rstrip('/')
            validated_data['url_publique'] = f'{base}/news/{news.slug}'

        return models.LienPublication.objects.create(
            **validated_data,
            mot_de_passe_hash=make_password(mot_de_passe) if mot_de_passe else '',
            scope_etablissement=scope.get('etablissement', ''),
            scope_province=scope.get('province', ''),
            scope_promotion=scope.get('promotion', ''),
            scope_organisation=scope.get('organisation', ''),
            scope_classe=scope.get('classe', ''),
        )
