from rest_framework import permissions

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