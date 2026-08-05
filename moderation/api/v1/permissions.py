from rest_framework.permissions import BasePermission

from common.permissions import a_role, ROLES_MODERATION


class SignalementPermission(BasePermission):
    """Créer un signalement : tout utilisateur authentifié. Lister/traiter :
    modérateurs/administrateurs uniquement."""

    def has_permission(self, request, view):
        if view.action == 'create':
            return bool(request.user and request.user.is_authenticated)
        return a_role(request.user, *ROLES_MODERATION)
