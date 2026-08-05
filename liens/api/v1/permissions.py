from rest_framework.permissions import SAFE_METHODS, BasePermission

from common.permissions import a_role, ROLES_MODERATION


class LienPublicationPermission(BasePermission):
    """Génération d'un lien de partage : tout utilisateur authentifié
    (voir PERMISSIONS.LIEN_CREATE, accordé dès le rôle étudiant côté
    frontend — src/lib/permissions/rolePermissions.ts). Suppression :
    propriétaire ou modérateur/administrateur (voir PERMISSIONS.LIEN_DELETE)."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if a_role(request.user, *ROLES_MODERATION):
            return True
        return obj.cree_par_id == request.user.id
