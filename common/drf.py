"""
Utilitaires DRF communs à toutes les API des systèmes métier (A1..E3).
"""

from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend


class SocleModelViewSet(viewsets.ModelViewSet):
    """ModelViewSet de base : trace automatiquement l'utilisateur courant
    comme Créé par / Modifié par sur le Socle de Traçabilité, et exclut par
    défaut les entités supprimées logiquement des listings."""

    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        qs = self.queryset if self.queryset is not None else self.serializer_class.Meta.model.objects.all()
        if self.request.query_params.get('inclure_supprimes') == 'true':
            return qs
        return qs.filter(supprime_le__isnull=True)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(cree_par=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(modifie_par=user)

    def perform_destroy(self, instance):
        # Jamais de suppression physique : suppression logique systématique.
        user = self.request.user if self.request.user.is_authenticated else None
        instance.supprimer_logiquement(utilisateur=user)


class LectureSeuleModelViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet en lecture seule, pour les journaux immuables (E2.1, E3.1)."""
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
