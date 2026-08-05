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
