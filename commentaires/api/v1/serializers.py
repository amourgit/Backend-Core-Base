from django.db.models import Count, Q
from rest_framework import serializers

from users.api.v1.serializers import UtilisateurPublicSerializer
from ... import models


class MediaJointSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    url = serializers.SerializerMethodField()

    class Meta:
        model = models.MediaJointCommentaire
        fields = ('id', 'type', 'url')

    def get_url(self, obj):
        request = self.context.get('request')
        if obj.fichier:
            return request.build_absolute_uri(obj.fichier.url) if request else obj.fichier.url
        return obj.url_externe


class CommentaireSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    news_id = serializers.CharField(read_only=True)
    sujet_id = serializers.CharField(source='news_id', read_only=True)
    # Dénormalisent le strict nécessaire pour afficher/lier "mes
    # commentaires" (page Profil, onglet Journal d'activité) sans que le
    # frontend n'ait à refaire un aller-retour par news_id pour chaque
    # commentaire listé (évite un N+1 côté client).
    news_titre = serializers.CharField(source='news.titre', read_only=True)
    news_slug = serializers.CharField(source='news.slug', read_only=True)
    auteur = UtilisateurPublicSerializer(read_only=True)
    type_contenu = serializers.CharField(required=False)
    audio_url = serializers.SerializerMethodField()
    media = MediaJointSerializer(source='medias', many=True, read_only=True)
    reponse_a = serializers.SerializerMethodField()
    mentions = serializers.SlugRelatedField(slug_field='username', many=True, read_only=True)
    reactions = serializers.SerializerMethodField()
    user_reactions = serializers.SerializerMethodField()
    votes = serializers.SerializerMethodField()
    user_vote_status = serializers.SerializerMethodField()
    est_administrateur = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)

    class Meta:
        model = models.Commentaire
        fields = (
            'id', 'news_id', 'sujet_id', 'news_titre', 'news_slug', 'auteur', 'type_contenu', 'audio_url',
            'audio_duration', 'contenu', 'media', 'reponse_a', 'mentions', 'reactions', 'user_reactions',
            'votes', 'user_vote_status', 'est_epingle', 'est_reponse_acceptee', 'est_administrateur',
            'created_at',
        )

    def get_audio_url(self, obj):
        if not obj.audio_fichier:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.audio_fichier.url) if request else obj.audio_fichier.url

    def get_reponse_a(self, obj):
        return str(obj.reponse_a_id) if obj.reponse_a_id else None

    def get_reactions(self, obj):
        return dict(obj.reactions.values_list('type_reaction').annotate(total=Count('id')).order_by())

    def get_user_reactions(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return []
        return list(obj.reactions.filter(utilisateur=user).values_list('type_reaction', flat=True))

    def get_votes(self, obj):
        agg = obj.votes.aggregate(
            up=Count('id', filter=Q(direction=models.VoteCommentaire.Direction.UP)),
            down=Count('id', filter=Q(direction=models.VoteCommentaire.Direction.DOWN)),
        )
        return (agg['up'] or 0) - (agg['down'] or 0)

    def get_user_vote_status(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return None
        vote = obj.votes.filter(utilisateur=user).first()
        return vote.direction if vote else None

    def get_est_administrateur(self, obj):
        return getattr(obj.auteur, 'role', None) in ('administrateur', 'moderateur')


class CommentaireEcritureSerializer(serializers.ModelSerializer):
    reponse_a = serializers.PrimaryKeyRelatedField(
        queryset=models.Commentaire.objects.all(), required=False, allow_null=True,
    )

    class Meta:
        model = models.Commentaire
        # 'id' DOIT être listé ici : CommentaireViewSet.create() (ci-dessous)
        # relit response.data['id'] juste après super().create() pour
        # renvoyer la représentation complète (CommentaireSerializer, avec
        # auteur/reactions/etc.) -- sans 'id' dans ce serializer d'écriture,
        # response.data ne contient jamais cette clé et la création plante
        # systématiquement avec KeyError: 'id'.
        fields = ('id', 'contenu', 'type_contenu', 'audio_duration', 'reponse_a')
        extra_kwargs = {'contenu': {'required': False, 'allow_blank': True}}
