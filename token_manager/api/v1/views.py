from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from django.contrib.auth import get_user_model
from django_tenants.utils import schema_context
from token_manager.models import TokenSettings, TokenManager
from .serialisers import (
    TokenSettingsSerializer,
    TokenManagerSerializer,
    TokenObtenSerializer,
    TokenRefreshSerializer,
)
from datetime import timedelta
from .utils import check_and_revoke_token_if_expired, check_token_settings
from config.fonction import request_header_token, minute_to_seconde
from tenants.models import Tenant
import logging
from rest_framework_simplejwt.views import TokenRefreshView, TokenObtainPairView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework.viewsets import ModelViewSet
from django.utils import timezone
from user_agents import parse
import hashlib
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db import connection
from tenants.api.v1.services import TenantService
from domain.api.v1.services import DomainService
from users.api.v1.services import UsersService
from .services import TokenService
from django.core.exceptions import ObjectDoesNotExist
logger = logging.getLogger(__name__)
User = get_user_model()


class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = []
    authentication_classes = []
    @method_decorator(csrf_exempt)
    def post(self, request, *args, **kwargs):
        ###### 1. Verification de l'existance des paramettres token en base de donees
        formatReponse, stat, settings_token_actif = check_token_settings()
        if not stat:
            return Response(formatReponse, status=formatReponse['status'])

        ###### 2. Verification de l'ensemble de doneees en entrée
        # 1.1 Verification de la conformite des doneees en entrée dans le serializer
        serializer = TokenObtenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = request.data.get('username')
        password = request.data.get('password')

        # 1.2 Verification de la conformite du tenant par le sous-domaine dans l'URL
        tenant, formatReponse = TenantService.get_tenant_by_sous_domaine_actif(request)
        if tenant is None:
            return Response(formatReponse, int(formatReponse['status']))


        ###### 2. Verification des donnees entrees en Base de donnees
        with schema_context(tenant.schema_name):
            # 2.1 Verification de l'existance de l'utilisateur dans le tenant
            formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)  
            try:
                user = User.objects.get(username=username)
                if not user.check_password(password):
                    formatReponse['message'] = "Le username ou password est incorrect"
                    return Response(formatReponse, formatReponse['status'])
            except User.DoesNotExist:
                formatReponse['message'] = "Le username ou password est incorrect"
                return Response(formatReponse,  formatReponse['status'])
            except Exception as e:
                formatReponse['titre'] = 'Erreur Interne'
                formatReponse['message'] = "Erreur lors de la verification des donnees en base de donnees. Veuillez contacter l'administrateur"
                formatReponse['status'] = int(status.HTTP_500_INTERNAL_SERVER_ERROR)
                return Response(formatReponse, formatReponse['status'])
            
        ###### 2. Verification si actif ou pas.
        if not user.is_active:
            formatReponse['titre'] = 'Hors Service'
            formatReponse['message'] = "Votre compte est hors service! Veuillez contacter votre administrateur."
            return Response(formatReponse,  formatReponse['status'])
        
        ###### 3. Recuperations des Informations si Username et Password verifies
        user_agent_str = request.META.get('HTTP_USER_AGENT', '')
        user_agent = parse(user_agent_str)
        ip_address = self._get_client_ip(request)
        device_id = hashlib.md5(f"{ip_address}{user_agent_str}".encode()).hexdigest()

        ##### 4. Revoker tous les token actif du device courant (Eviter plusieurs token actif pour le meme device. sauf pour des devices differents)
        try:
            TokenService.update_all_token_by_perform(
                {
                    'user_id': user.id,
                    'tenant_id': tenant.id,
                    'device_id': device_id,
                    'is_revoked': False
                },
                {
                    'revoked_at': timezone.now(),
                    'is_revoked': True,
                    'is_current': False,
                    # 'last_used': timezone.now()
                }
            )
        except Exception as e:
            logger.error(f"Erreur lors de la révocation des tokens actif du device {str(device_id)}: {str(e)}")

        ##### 5. Creation du nouveau access_token actif et son refresh_token (token) pour ce device en rapport avec l'utilisateur courant
        refresh = RefreshToken.for_user(user)
        refresh['tenant'] = tenant.schema_name
        refresh['tenant_id'] = tenant.id
        # print(settings_token_actif.access_token_lifetime, settings_token_actif.refresh_token_lifetime)
        refresh.set_exp(lifetime=timedelta(minutes=int(settings_token_actif.refresh_token_lifetime)))
        refresh.access_token.set_exp(lifetime=timedelta(minutes=int(settings_token_actif.access_token_lifetime)))
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        ##### 6. Stockage du nouveau token dans la base de donnees
        token_manager = TokenService.create_token(
            {
            'user_id': user.id,
            'username': user.username,
            'tenant_id': tenant.id,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': timezone.now() + timezone.timedelta(minutes=settings_token_actif.access_token_lifetime),
            'ip_address': ip_address,
            'device_id': device_id,
            'device_family': user_agent.device.family,
            'device_brand': user_agent.device.brand,
            'device_model': user_agent.device.model,
            'device_type': (
                'mobile' if user_agent.is_mobile else
                'tablet' if user_agent.is_tablet else
                'desktop' if user_agent.is_pc else
                'other'
            ),
            'os_family': user_agent.os.family,
            'browser_family': user_agent.browser.family,
            'user_agent': user_agent_str,
            'is_current': True
            }
        )
        
        ##### 7. marquer ce token comme courant et actif pour ce device
        token_manager.mark_as_current()

        ##### 8. Renvoie de la reponse si toutes les actions effectuees sans erreurs
        return Response({
            'access': access_token,
            'refresh': refresh_token,
            'device_info': token_manager.get_device_info()
        })

    # Recuperation de l'adress IP du client lors de la requette
    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = []
    authentication_classes = []
    @method_decorator(csrf_exempt)
    def post(self, request, *args, **kwargs):
        
        formatReponse, stat, settings_token_actif = check_token_settings()
        if not stat:
            return Response(formatReponse, status=formatReponse['status'])
        
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data.get('refresh')  

        # 3. Verification de la conformite du tenant par le sous-domaine dans l'URL
        tenant, formatReponse = TenantService.get_tenant_by_sous_domaine_actif(request)
        if tenant is None:
            return Response(formatReponse, int(formatReponse['status']))
        
        try:            
            # 3. Vérifier que le refresh_token est valide et appartient au bon tenant
            token_manager, formatReponse = TokenService.get_token_by_choice_data(
                {
                    'tenant_id': tenant.id,
                    'refresh_token': refresh_token,
                    'is_revoked': False,
                    'is_current': True,
                }
            )
            if token_manager is None:
                return Response(formatReponse, int(formatReponse['status']))
            
            # 5. Si toutes les vérifications sont passées, procéder au refresh
            response = super().post(request, *args, **kwargs)
            
            if response.status_code == 200:
                try:
                    new_access_token = response.data.get('access')
                    new_refresh_token = response.data.get('refresh')  # Récupérer le nouveau refresh token

                    # 6. Décoder le refresh token pour obtenir les informations utilisateur
                    refresh_token_obj = RefreshToken(new_refresh_token)
                    user_id = refresh_token_obj['user_id']
                    
                    # 7. Récupérer l'utilisateur depuis la base de données (schéma tenant)
                    try:
                        # En S'assurant que nous sommes dans le schéma du tenant
                        with schema_context(tenant.schema_name):
                            user = User.objects.get(id=user_id)
                            username = user.username
                    except User.DoesNotExist:
                        return Response(
                            {'error': 'Utilisateur non trouvé'},
                            status=status.HTTP_401_UNAUTHORIZED
                        )
                    
                    # 8. Get device information
                    user_agent_str = request.META.get('HTTP_USER_AGENT', '')
                    user_agent = parse(user_agent_str)
                    ip_address = self._get_client_ip(request)
                    device_id = hashlib.md5(f"{ip_address}{user_agent_str}".encode()).hexdigest()

                    # 9. Créer un nouveau token manager avec toutes les informations
                    new_token_manager = TokenService.create_token(
                        {
                        'user_id': user_id,
                        'username': username,
                        'tenant_id': tenant.id,
                        'access_token': new_access_token,
                        'refresh_token': new_refresh_token,
                        'expires_at': timezone.now() + timezone.timedelta(minutes=5),
                        'ip_address': ip_address,
                        'device_id': device_id,
                        'device_family': user_agent.device.family,
                        'device_brand': user_agent.device.brand,
                        'device_model': user_agent.device.model,
                        'device_type': (
                            'mobile' if user_agent.is_mobile else
                            'tablet' if user_agent.is_tablet else
                            'desktop' if user_agent.is_pc else
                            'other'
                            ),
                        'os_family': user_agent.os.family,
                        'browser_family': user_agent.browser.family,
                        'user_agent': user_agent_str,
                        'is_current': True
                        }
                    )
                    
                    new_token_manager.mark_as_current()

                    response.data['device_info'] = new_token_manager.get_device_info()
                except Exception as e:
                    return Response(
                        {'error': 'Error during token refresh'},
                        status=status.HTTP_401_UNAUTHORIZED
                    )

            return response

        except Exception as e:
            return Response(
                {'error': 'Invalid refresh token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class LogoutView(APIView):
    permission_classes = []
    authentication_classes = []
    @swagger_auto_schema(
        operation_description="Déconnexion de l'utilisateur et révocation du token",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'access_token': openapi.Schema(type=openapi.TYPE_STRING, description="Access token JWT"),
            },
            required=['access_token']
        ),
        responses={
            200: openapi.Response(
                description="Déconnexion réussie",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'message': openapi.Schema(type=openapi.TYPE_STRING, description="Message de succès"),
                    }
                )
            ),
            400: "Token invalide ou déjà révoqué",
            401: "Non authentifié"
        }
    )
    def post(self, request):
        formatReponse, stat, settings_token_actif = check_token_settings()
        if not stat:
            return Response(formatReponse, status=formatReponse['status'])

        # 1.2 Verification de la conformite du tenant par le sous-domaine dans l'URL
        tenant, formatReponse = TenantService.get_tenant_by_sous_domaine_actif(request)
        if tenant is None:
            return Response(formatReponse, int(formatReponse['status']))
        
        #  1. Récupérer l'access_token dans le Header de la requette
        access_token, formatReponse = request_header_token(request)
        if access_token is None:
            formatReponse['message'] = "Le access_token n'existe pas dans le header de la requette"
            return Response(formatReponse, int(formatReponse['status']))
        
        try:
            # 4. Vérifier que le token existe dans notre base de données
            token_obj, formatReponse = TokenService.get_token_by_choice_data(
                {
                    'tenant_id': tenant.id,
                    'access_token': access_token,
                    'is_current': True,
                    'is_revoked': False
                }
            )
            if token_obj is None:
                formatReponse['message'] = "Le access token n'est pas valide ou a deja ete revoque"
                return Response(formatReponse, int(formatReponse['status']))

            token_obj.revoke()
            token_obj.save()

            return Response({"message": "Déconnexion réussie"}, status=200)

        except Exception as e:
            logger.error(f"Erreur lors de la déconnexion: {str(e)}")
            return Response({"error": "Erreur lors de la déconnexion"}, status=500)



class TokenSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet pour la gestion des paramètres de tokens
    """
    queryset = TokenSettings.objects.all()
    serializer_class = TokenSettingsSerializer
    permission_classes = [IsAuthenticated]

class TokenManagerViewSet(ModelViewSet):
    """
    ViewSet pour gérer les tokens
    """
    serializer_class = TokenManagerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return TokenManager.objects.none()

        # Récupérer le tenant_id depuis le token de l'utilisateur authentifié
        tenant_id = self.request.auth.payload.get('tenant_id')
        if not tenant_id:
            return TokenManager.objects.none()

        # Filtrer les tokens par tenant_id
        queryset = TokenManager.objects.filter(tenant_id=tenant_id)

        # Si l'utilisateur n'est pas superuser, ne montrer que ses propres tokens
        if not self.request.user.is_superuser:
            user_id = self.request.auth.payload.get('user_id')
            queryset = queryset.filter(user_id=user_id)

        return queryset.order_by('-created_at')

    @swagger_auto_schema(
        operation_description="Liste tous les tokens de l'utilisateur",
        responses={
            200: openapi.Response(
                description="Liste des tokens",
                schema=openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'jti': openapi.Schema(type=openapi.TYPE_STRING),
                            'tenant_id': openapi.Schema(type=openapi.TYPE_STRING),
                            'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                            'username': openapi.Schema(type=openapi.TYPE_STRING),
                            'access_token': openapi.Schema(type=openapi.TYPE_STRING),
                            'refresh_token': openapi.Schema(type=openapi.TYPE_STRING),
                            'ip_address': openapi.Schema(type=openapi.TYPE_STRING),
                            'user_agent': openapi.Schema(type=openapi.TYPE_STRING),
                            'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            'expires_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            'last_used_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            'is_revoked': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                            'revoked_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                        }
                    )
                )
            ),
            401: "Non authentifié"
        }
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Vérifier que le token appartient bien au tenant et à l'utilisateur
        if not request.user.is_superuser:
            if instance.tenant_id != request.auth.payload.get('tenant_id') or \
               instance.user_id != request.auth.payload.get('user_id'):
                return Response(
                    {"detail": "Vous n'avez pas la permission d'accéder à ce token"},
                    status=status.HTTP_403_FORBIDDEN
                )
        return super().retrieve(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Vérifier que le token appartient bien au tenant et à l'utilisateur
        if not request.user.is_superuser:
            if instance.tenant_id != request.auth.payload.get('tenant_id') or \
               instance.user_id != request.auth.payload.get('user_id'):
                return Response(
                    {"detail": "Vous n'avez pas la permission de supprimer ce token"},
                    status=status.HTTP_403_FORBIDDEN
                )
        return super().destroy(request, *args, **kwargs)

class SessionManagementView(APIView):
    def get(self, request, session_id=None):
        ###### 1. Verification de l'existance du tenant
        
        # 2.1 Tentative de détection manuelle du tenant par le sous-domaine
        sous_domaine = DomainService.get_sous_domaine_by_request(request)           
        try:
            tenant = TenantService.get_tenant_by_sous_domaine_actif(sous_domaine=sous_domaine)
        except Tenant.DoesNotExist:
            return Response(
                {'error': 'Tenant not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        is_unique = True if session_id else False

        # Recuperation de l'utilisateur grace au token
        access_token = TokenService.get_token_from_header(request)
        token = AccessToken(access_token)
        user_id = token.user_id

        # 2. Recuperations des Token valide et actif de l'Utilisateur dans son tenant
        sessions = TokenService.get_all_token_by_perform(
            {
                'user_id': user_id,
                'tenant_id': tenant.id,
                'is_revoked': False,
                'expires_at__gt': timezone.now()
            },
            is_unique=is_unique
        ).order_by('-last_used')

        if is_unique:
            return Response({
                'session': sessions.first().get_device_info()
            })
        else:
            return Response({
                'sessions': [{
                    'id': session.id,
                    'device_info': session.get_device_info(),
                    'created_at': session.created_at,
                    'last_used': session.last_used,
                    'is_current': session.is_current,
                    'device_id': session.device_id,
                    'device_family': session.device_family,
                    'device_brand': session.device_brand,
                    'device_model': session.device_model,
                    'device_type': session.device_type,
                    'os_family': session.os_family,
                    'browser_family': session.browser_family,
                    'user_agent': session.user_agent,
                    'ip_address': session.ip_address,
                    'expires_at': session.expires_at,
                    'last_used_at': session.last_used_at,
                    'is_revoked': session.is_revoked,
                    'revoked_at': session.revoked_at,
                } for session in sessions]
            })

    def delete(self, request, session_id=None):
        # 1. Verification de l'existance du tenant
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            # 2.1 Tentative de détection manuelle du tenant par le sous-domaine
            sous_domaine = DomainService.get_sous_domaine_by_request(request)           
            try:
                tenant = TenantService.get_tenant_by_sous_domaine_actif(sous_domaine=sous_domaine)
            except Tenant.DoesNotExist:
                return Response(
                    {'error': 'Tenant not found'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # 2. Verification de l'existance de la session
        if session_id:
            try:
                session = TokenManager.objects.get(
                    id=session_id,
                    user_id=request.user.id,
                    tenant_id=tenant.id
                )
                if session.is_current:
                    return Response(
                        {'error': 'Cannot revoke current session'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                session.revoke()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except TokenManager.DoesNotExist:
                return Response(
                    {'error': 'Session not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            TokenManager.objects.filter(
                user_id=request.user.id,
                tenant_id=tenant.id,
                is_current=False
            ).update(
                is_revoked=True,
                revoked_at=timezone.now()
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        



class checkTokenView(APIView):
    permission_classes = []
    authentication_classes = []
    def post(self, request):
        formatReponse, stat, settings_token_actif = check_token_settings()
        if not stat:
            return Response(formatReponse, status=formatReponse['status'])

        access_token = request.data.get('access_token')
        refresh_token = request.data.get('refresh_token')
        if not access_token or not refresh_token:
            formatReponse['type'] = 'error'
            formatReponse['titre'] = 'Informations Manquante'
            formatReponse['niveau'] = 100
            formatReponse['message'] = "Le refresh_token et l'access_token sont requis"
            formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)
            return Response(formatReponse, status=formatReponse['status'])
        
        reponse, stat = check_and_revoke_token_if_expired({
            'access_token': access_token,
            'refresh_token': refresh_token,
        })
        return Response(reponse, status=status.HTTP_200_OK)