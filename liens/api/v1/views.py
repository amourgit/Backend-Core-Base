from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from common.drf import SocleModelViewSet
from ... import models
from . import services
from .permissions import LienPublicationPermission
from .serializers import LienPublicationSerializer, LienPublicationEcritureSerializer


class LienPublicationViewSet(SocleModelViewSet):
    """
    - GET/POST /liens/v1/liens/?news={id}
    - GET/DELETE /liens/v1/liens/{id}/
    - POST /liens/v1/liens/{id}/acceder/   {typeAcces: 'clic'|'scan'} (tracking, endpoint public)
    """
    permission_classes = [LienPublicationPermission]
    filterset_fields = ['news']

    def get_queryset(self):
        return models.LienPublication.objects.actifs().select_related('news').prefetch_related('acces')

    def get_serializer_class(self):
        if self.action == 'create':
            return LienPublicationEcritureSerializer
        return LienPublicationSerializer

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        lien = models.LienPublication.objects.get(pk=response.data['id'])
        return Response(LienPublicationSerializer(lien, context={'request': request}).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='acceder', permission_classes=[])
    def acceder(self, request, pk=None):
        """Endpoint public (pas d'authentification requise) : trace un clic/scan."""
        lien = self.get_object()
        type_acces = request.data.get('type_acces', models.LienAcces.TypeAcces.CLIC)
        services.enregistrer_acces(lien, type_acces, adresse_ip=request.META.get('REMOTE_ADDR'))
        return Response({
            'valide': services.lien_est_valide(lien),
            'aMotDePasse': lien.a_mot_de_passe,
        })
