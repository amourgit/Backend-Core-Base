from rest_framework import permissions
from common.permissions import a_role
from users.models import RoleUtilisateur


class EstAdministrateurDuTenant(permissions.BasePermission):
    """
    Accès réservé au rôle applicatif ADMINISTRATEUR (ou superuser Django) —
    voir `common.permissions.a_role`. Utilisée pour les endpoints
    d'identité et de documents du tenant (`TenantInformationsPrimaires`,
    `TenantDocumentRequis`, `TenantDocumentGenerique`) : des données
    légales/administratives sensibles qui ne concernent pas la
    modération de contenu (d'où un rôle dédié plutôt que
    `common.permissions.EstModerateurOuAdmin`).
    """
    def has_permission(self, request, view):
        return a_role(request.user, RoleUtilisateur.ADMINISTRATEUR)


class IsTenantAdmin(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est un administrateur du tenant
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff

class IsTenantUser(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur appartient au tenant
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

class IsPublicEndpoint(permissions.BasePermission):
    """
    Permission pour les endpoints publics
    """
    def has_permission(self, request, view):
        return True