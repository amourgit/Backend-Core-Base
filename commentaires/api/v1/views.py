from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf import SocleModelViewSet
from ... import models
from . import services
from .permissions import CommentairePermission
from .serializers import CommentaireSerializer, CommentaireEcritureSerializer


class CommentaireViewSet(SocleModelViewSet):
    """
    - GET  /commentaires/v1/commentaires/?news={id}&tri=recents|populaires|pertinents
    - POST /commentaires/v1/commentaires/                (body: {news, contenu, ...})
    - GET/PATCH/DELETE /commentaires/v1/commentaires/{id}/
    - POST /commentaires/v1/commentaires/{id}/vote/       {direction: 'up'|'down'}
    - POST /commentaires/v1/commentaires/{id}/reactions/  {reaction: '...'}
    - POST /commentaires/v1/commentaires/{id}/pin/        {estEpingle: bool}
    """
    permission_classes = [CommentairePermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['news', 'reponse_a']
    ordering_fields = ['cree_le']
    ordering = ['-cree_le']

    def get_queryset(self):
        qs = models.Commentaire.objects.actifs().select_related('auteur', 'reponse_a').prefetch_related(
            'medias', 'reactions', 'votes', 'mentions',
        )
        if getattr(self, 'swagger_fake_view', False):
            return qs.none()

        tri = self.request.query_params.get('tri')
        if tri == 'populaires':
            from django.db.models import Count, Q
            return qs.annotate(
                score=Count('votes', filter=Q(votes__direction='up')) - Count('votes', filter=Q(votes__direction='down'))
            ).order_by('-score')
        if tri == 'pertinents':
            return qs.order_by('-est_epingle', '-est_reponse_acceptee', '-cree_le')
        return qs.order_by('-cree_le')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return CommentaireEcritureSerializer
        return CommentaireSerializer

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        user = self.request.user
        news_id = self.request.data.get('news')
        if not news_id:
            raise ValidationError({'news': "Ce champ est requis (identifiant de la News commentée)."})
        contenu = serializer.validated_data.get('contenu', '')
        commentaire = serializer.save(auteur=user, cree_par=user, news_id=news_id)
        mentions = services.extraire_mentions(contenu)
        if mentions:
            commentaire.mentions.set(mentions)
            from notifications.api.v1 import services as notifications_services
            for utilisateur_mentionne in mentions:
                if utilisateur_mentionne.pk != user.pk:
                    notifications_services.notifier_mention(commentaire, utilisateur_mentionne)

    def perform_update(self, serializer):
        serializer.save(modifie_par=self.request.user, motif_derniere_modification='Édition via API')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = CommentaireSerializer(instance, context={'request': request})
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Renvoie la représentation complète (avec auteur, reactions, etc.)
        commentaire = models.Commentaire.objects.get(pk=response.data['id'])
        return Response(
            CommentaireSerializer(commentaire, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        commentaire = self.get_object()
        direction = request.data.get('direction')
        if direction not in models.VoteCommentaire.Direction.values:
            return Response({'detail': 'Direction invalide.'}, status=status.HTTP_400_BAD_REQUEST)
        services.basculer_vote(commentaire, request.user, direction)
        return Response(CommentaireSerializer(commentaire, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path='reactions')
    def reagir(self, request, pk=None):
        commentaire = self.get_object()
        type_reaction = request.data.get('reaction')
        if not type_reaction:
            return Response({'detail': 'reaction requis.'}, status=status.HTTP_400_BAD_REQUEST)
        services.basculer_reaction(commentaire, request.user, type_reaction)
        return Response(CommentaireSerializer(commentaire, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def pin(self, request, pk=None):
        commentaire = self.get_object()
        commentaire.est_epingle = bool(request.data.get('estEpingle', not commentaire.est_epingle))
        commentaire.save(update_fields=['est_epingle'])
        return Response(CommentaireSerializer(commentaire, context={'request': request}).data)
