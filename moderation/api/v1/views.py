from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from common.drf import SocleModelViewSet
from common.permissions import EstModerateurOuAdmin
from journal.models import EvenementJournal, TypeActionJournal
from users.api.v1.serializers import UtilisateurPublicSerializer
from ... import models
from .permissions import SignalementPermission
from .serializers import SignalementSerializer, SignalementEcritureSerializer


class SignalementViewSet(SocleModelViewSet):
    """
    - POST /moderation/v1/signalements/                (tout utilisateur connecté)
    - GET  /moderation/v1/signalements/                 (modérateurs/administrateurs)
    - POST /moderation/v1/signalements/{id}/traiter/    {statut: 'traite'|'rejete'}
    """
    permission_classes = [SignalementPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['statut', 'motif', 'type_contenu']

    def get_queryset(self):
        return models.Signalement.objects.actifs().select_related('auteur_signalement').order_by('-cree_le')

    def get_serializer_class(self):
        if self.action == 'create':
            return SignalementEcritureSerializer
        return SignalementSerializer

    def perform_create(self, serializer):
        serializer.save(auteur_signalement=self.request.user, cree_par=self.request.user)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        signalement = models.Signalement.objects.get(pk=response.data['id'])
        return Response(SignalementSerializer(signalement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def traiter(self, request, pk=None):
        signalement = self.get_object()
        statut = request.data.get('statut')
        if statut not in (models.SignalementStatutChoices.TRAITE, models.SignalementStatutChoices.REJETE):
            return Response({'detail': "statut doit être 'traite' ou 'rejete'."}, status=status.HTTP_400_BAD_REQUEST)

        signalement.statut = statut
        signalement.modifie_par = request.user
        signalement.motif_derniere_modification = f'Signalement {statut} par {request.user}'
        signalement.save()

        EvenementJournal.consigner(
            action=TypeActionJournal.MODERATION,
            utilisateur=request.user,
            cible=signalement,
            cible_libelle=signalement.titre_ou_apercu,
            details={'statut': statut, 'motif': signalement.motif},
            adresse_ip=request.META.get('REMOTE_ADDR'),
        )

        return Response(SignalementSerializer(signalement).data)


class UtilisateursAdminViewSet(viewsets.ReadOnlyModelViewSet):
    """GET /moderation/v1/utilisateurs/ — annuaire utilisateurs pour le
    panneau d'administration (distinct de users/v1/users/, réservé aux
    superusers pour la gestion de comptes)."""
    serializer_class = UtilisateurPublicSerializer
    permission_classes = [EstModerateurOuAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['role']

    def get_queryset(self):
        from django.contrib.auth import get_user_model
        return get_user_model().objects.all().select_related('etablissement').prefetch_related('badges').order_by('username')
