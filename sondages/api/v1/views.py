from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from common.drf import SocleModelViewSet
from ... import models
from . import services
from .permissions import SondagePermission
from .serializers import SondageSerializer, SondageEcritureSerializer


class SondageViewSet(SocleModelViewSet):
    """
    - GET/POST /sondages/v1/sondages/
    - GET/PATCH/DELETE /sondages/v1/sondages/{id}/
    - POST /sondages/v1/sondages/{id}/vote/   {choixIds: string[]}
    - GET /sondages/v1/sondages/mes-votes/    sondages auxquels l'utilisateur
      courant a participé (page Profil, onglet Historique des votes) --
      SondageSerializer.user_voted_choice_ids indique déjà le(s) choix
      exact(s) de l'utilisateur pour chacun.
    """
    permission_classes = [SondagePermission]
    filterset_fields = ['news', 'statut']

    def get_queryset(self):
        return models.Sondage.objects.actifs().select_related('news').prefetch_related('choix', 'votes')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return SondageEcritureSerializer
        return SondageSerializer

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        sondage = models.Sondage.objects.get(pk=response.data['id'])
        return Response(SondageSerializer(sondage, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        sondage = self.get_object()
        # Le parser JSON convertit déjà `choixIds` (camelCase, envoyé par
        # le frontend) en `choix_ids` avant que la vue ne le reçoive.
        choix_ids = request.data.get('choix_ids') or []
        services.enregistrer_vote(sondage, request.user, choix_ids)
        return Response(SondageSerializer(sondage, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='mes-votes')
    def mes_votes(self, request):
        """Sondages où l'utilisateur courant a voté au moins une fois --
        un visiteur anonyme n'a par définition voté nulle part, donc une
        liste vide plutôt qu'un 401 (cohérent avec le reste de l'API,
        toujours accessible sans session -- voir config/config.py)."""
        if not (request.user and request.user.is_authenticated):
            return Response([])
        queryset = self.filter_queryset(
            self.get_queryset().filter(votes__utilisateur=request.user).distinct()
        )
        serializer = SondageSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
