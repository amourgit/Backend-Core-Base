from django.core.exceptions import PermissionDenied
from django.db import connection
from django.utils.translation import gettext_lazy as _
from rest_framework import viewsets

from common.admin import est_schema_public
from common.drf import SocleModelViewSet


class SharedTenantScopedModelViewSet(SocleModelViewSet):
    """
    `SocleModelViewSet` (common/drf.py) pour un modèle SHARED_APPS
    (schéma public) rattaché à UN tenant par ligne (champ `tenant`), en
    libre-service DEPUIS ce tenant — cas de
    `TenantInformationsPrimaires`/`TenantDocumentRequis`/
    `TenantDocumentGenerique` (voir la note d'architecture en tête de
    `tenants/models.py`).

    Combine deux responsabilités :
      1. Filtrage/assignation par tenant courant (`request.tenant`, posé
         par `tenants.middleware.TenantMiddleware` sur CHAQUE requête) —
         même idée que `TenantViewSetMixin` ci-dessous, mais fusionnée
         ici plutôt que composée par héritage multiple, pour ne pas avoir
         deux `perform_create` en compétition dans l'ordre de résolution
         de méthode.
      2. Traçabilité Socle sûre du point de vue schéma :
         `SocleModelViewSet.perform_create`/`perform_update` assignent
         `cree_par`/`modifie_par` = `request.user` sans condition — valide
         pour un modèle TENANT_APPS, PAS ici (voir le docstring détaillé
         dans `tenants/models.py`). On n'assigne la vraie FK que depuis le
         schéma public ; sinon on trace l'acteur dans les champs texte
         libres `cree_par_systeme`/`modifie_par_systeme` prévus par le
         Socle pour exactement ce cas.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return qs.none()
        return qs.filter(tenant=tenant)

    def _identifiant_acteur(self):
        request = self.request
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated):
            return ''
        nom = user.get_username() if hasattr(user, 'get_username') else str(user.pk)
        return f"tenant:{connection.schema_name}:{nom or user.pk}"

    def perform_create(self, serializer):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            raise PermissionDenied(_('Tenant non résolu pour cette requête.'))
        if est_schema_public():
            user = self.request.user if self.request.user.is_authenticated else None
            serializer.save(tenant=tenant, cree_par=user)
        else:
            serializer.save(tenant=tenant, cree_par_systeme=self._identifiant_acteur())

    def perform_update(self, serializer):
        if est_schema_public():
            user = self.request.user if self.request.user.is_authenticated else None
            serializer.save(modifie_par=user)
        else:
            serializer.save(modifie_par_systeme=self._identifiant_acteur())


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