from rest_framework import permissions
from rest_framework_simplejwt.authentication import JWTAuthentication
# from django_tenants.utils import get_current_tenant
from config.fonction import request_header_token
from tenants.api.v1.services import TenantService
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from token_manager.api.v1.services import TokenService



class IsTokenOwner(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur est propriétaire du token
    """
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user

class IsTokenSettingsAdmin(permissions.BasePermission):
    """
    Permission pour vérifier si l'utilisateur peut gérer les paramètres de token
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        return request.user.is_staff

class IsAccessTokenTenant(permissions.BasePermission):
    def has_permission(self, request, view):
        # 1.2 Verification de la conformite du tenant par le sous-domaine dans l'URL
        tenant, formatReponse = TenantService.get_tenant_by_sous_domaine_actif(request)
        if not tenant:
            return False
        
        access_token, formatReponse = request_header_token(request)
        if not access_token:
            return False

        token = AccessToken(access_token)
        if not token:
            return False
        
        # print(token.payload)

        if token.payload['tenant_id'] != tenant.id:
            return False
        
        # 3. Vérifier que le refresh_token est valide et appartient au bon tenant
        token_manager, formatReponse = TokenService.get_token_by_choice_data(
            {
                'tenant_id': tenant.id,
                'access_token': access_token,
                'is_revoked': True,
                'is_current': False,
            }
        )
        if token_manager:
            return False

        return True

