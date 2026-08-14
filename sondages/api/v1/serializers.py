from django.db.models import Count
from rest_framework import serializers

from ... import models


class ChoixSondageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    image = serializers.SerializerMethodField()
    nombre_votes = serializers.SerializerMethodField()
    pourcentage = serializers.SerializerMethodField()

    class Meta:
        model = models.ChoixSondage
        fields = ('id', 'libelle', 'image', 'nombre_votes', 'pourcentage')

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def get_nombre_votes(self, obj):
        return obj.votes.count()

    def get_pourcentage(self, obj):
        total = self.context.get('total_votants') or 0
        if total == 0:
            return 0.0
        return round(obj.votes.count() / total * 100, 1)


class SondageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    news_id = serializers.CharField(read_only=True)
    sujet_id = serializers.CharField(source='news_id', read_only=True)
    image = serializers.SerializerMethodField()
    choix = serializers.SerializerMethodField()
    total_votes = serializers.SerializerMethodField()
    user_voted_choice_ids = serializers.SerializerMethodField()

    class Meta:
        model = models.Sondage
        fields = (
            'id', 'news_id', 'sujet_id', 'titre', 'description', 'question', 'image', 'choix',
            'date_debut', 'date_fin', 'type_vote', 'anonymat', 'visibilite_resultat', 'statut',
            'total_votes', 'user_voted_choice_ids',
        )

    def get_image(self, obj):
        if not obj.image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def _total_votants(self, obj):
        return obj.votes.values('utilisateur_id').distinct().count()

    def get_total_votes(self, obj):
        return self._total_votants(obj)

    def get_choix(self, obj):
        request = self.context.get('request')
        total = self._total_votants(obj)
        choix_qs = obj.choix.all()
        return ChoixSondageSerializer(choix_qs, many=True, context={'request': request, 'total_votants': total}).data

    def get_user_voted_choice_ids(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return []
        return list(obj.votes.filter(utilisateur=user).values_list('choix_id', flat=True))


class SondageEcritureSerializer(serializers.ModelSerializer):
    choix = serializers.ListField(child=serializers.CharField(max_length=255), write_only=True, required=False)

    class Meta:
        model = models.Sondage
        # 'id' DOIT être listé : SondageViewSet.create() (views.py) relit
        # response.data['id'] juste après super().create() -- même bug
        # que CommentaireEcritureSerializer (voir commentaires/api/v1/
        # serializers.py), corrigé à l'identique ici.
        fields = (
            'id', 'news', 'titre', 'description', 'question', 'image', 'choix',
            'date_debut', 'date_fin', 'type_vote', 'anonymat', 'visibilite_resultat', 'statut',
        )

    def create(self, validated_data):
        libelles_choix = validated_data.pop('choix', [])
        sondage = models.Sondage.objects.create(**validated_data)
        for ordre, libelle in enumerate(libelles_choix):
            models.ChoixSondage.objects.create(sondage=sondage, libelle=libelle, ordre=ordre)
        return sondage
