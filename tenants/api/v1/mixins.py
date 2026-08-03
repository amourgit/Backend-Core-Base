from django.core.exceptions import PermissionDenied
from rest_framework import viewsets

class TenantViewSetMixin(viewsets.ModelViewSet):
    """
    Mixin pour les ViewSets qui doivent être tenant-aware.
    """
    def get_queryset(self):
        """
        Filtre le queryset pour n'inclure que les objets du tenant actuel.
        """
        queryset = super().get_queryset()
        if hasattr(self.request, 'tenant'):
            return queryset.filter(tenant=self.request.tenant)
        return queryset.none()

    def perform_create(self, serializer):
        """
        Ajoute automatiquement le tenant lors de la création.
        """
        if not hasattr(self.request, 'tenant'):
            raise PermissionDenied("Tenant non spécifié")
        serializer.save(tenant=self.request.tenant) 