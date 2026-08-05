from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import a_role, ROLES_MODERATION


class CommentairePermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if view.action == 'pin':
            return a_role(request.user, *ROLES_MODERATION)
        if a_role(request.user, *ROLES_MODERATION):
            return True
        return obj.auteur_id == request.user.id
