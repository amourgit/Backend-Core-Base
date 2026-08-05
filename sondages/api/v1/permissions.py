from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import a_role, ROLES_MODERATION


class SondagePermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        if view.action == 'create':
            return a_role(request.user, 'organisation', *ROLES_MODERATION)
        # vote : tout utilisateur authentifié
        return bool(request.user and request.user.is_authenticated)
