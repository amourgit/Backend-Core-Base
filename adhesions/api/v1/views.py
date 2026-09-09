from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.permissions import EstModerateurOuAdmin
from adhesions.models import MembreTenant
from .serializers import MembreTenantSerializer, MembreTenantRoleUpdateSerializer, TraiterAdhesionSerializer
from .services import AdhesionService


class MembreTenantViewSet(viewsets.ModelViewSet):
    """
    - GET   /adhesions/v1/membres/             annuaire des membres de CE tenant (modérateurs/administrateurs)
    - GET   /adhesions/v1/membres/moi/          mon adhésion dans CE tenant (tout authentifié)
    - PATCH /adhesions/v1/membres/{id}/         changer rôle/organisation/établissement (modérateurs/administrateurs)
    - POST  /adhesions/v1/membres/{id}/traiter/ accepter/refuser une demande en_attente
    """
    queryset = (
        MembreTenant.objects
        .select_related('etablissement', 'organisation')
        .prefetch_related('badges')
        .order_by('-cree_le')
    )
    permission_classes = [EstModerateurOuAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['role', 'statut_adhesion']

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return MembreTenantRoleUpdateSerializer
        return MembreTenantSerializer

    def get_permissions(self):
        if self.action == 'moi':
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=['get'])
    def moi(self, request):
        membre = AdhesionService.get_membre(request.user.id)
        if membre is None:
            return Response({'detail': "Aucune adhésion dans ce tenant."}, status=status.HTTP_404_NOT_FOUND)
        return Response(MembreTenantSerializer(membre, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def traiter(self, request, pk=None):
        membre = self.get_object()
        serializer = TraiterAdhesionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AdhesionService.traiter_demande(
            membre,
            accepter=serializer.validated_data['accepter'],
            traite_par_user_id=request.user.id,
            motif=serializer.validated_data.get('motif', ''),
        )
        membre.refresh_from_db()
        return Response(MembreTenantSerializer(membre, context={'request': request}).data)
