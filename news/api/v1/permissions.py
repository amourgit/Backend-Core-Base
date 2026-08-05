"""
news/api/v1/permissions.py
=============================

Miroir côté backend du catalogue de permissions frontend
(src/lib/permissions/rolePermissions.ts) : défense en profondeur — le
frontend masque déjà l'UI, mais l'API ne fait jamais confiance au seul
client pour appliquer les règles d'autorisation.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import a_role, ROLES_MODERATION

ROLES_PEUVENT_CREER_NEWS = ('organisation',) + ROLES_MODERATION


class NewsPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if view.action == 'create':
            return a_role(request.user, *ROLES_PEUVENT_CREER_NEWS)
        # react / partager : tout utilisateur authentifié
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if a_role(request.user, *ROLES_MODERATION):
            return True
        return obj.auteur_id == request.user.id
