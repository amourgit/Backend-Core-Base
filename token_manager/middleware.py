from django.db import connection
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django_tenants.utils import get_public_schema_name
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from .api.v1.services import TokenService
from django.conf import settings
from config.config import GLOBAL_PUBLIC_ROUTES, TENANT_PUBLIC_ROUTES, AUTHENTICATED_ROUTES, ADMIN_ROUTES
import logging

logger = logging.getLogger(__name__)

class TenantJWTMiddleware(MiddlewareMixin):
    """
    Middleware responsable uniquement de l'authentification et de la sécurité.
    Responsabilités :
    - Authentification JWT
    - Validation des tokens dans le contexte tenant
    - Gestion des permissions (public, authentifié, admin)
    - Assignation de request.user
    """

    def __init__(self, get_response=None):
        super().__init__(get_response)
        self.jwt_auth = JWTAuthentication()

    def is_public_route(self, path):
        """
        Vérifie si la route est publique (pas d'authentification requise).

        IMPORTANT : ceci doit couvrir à la fois GLOBAL_PUBLIC_ROUTES (public,
        sans tenant : health/swagger/redoc) ET TENANT_PUBLIC_ROUTES (public,
        mais dans le contexte d'un tenant : login, refresh, check-token,
        création de tenant). tenants/middleware.py (TenantMiddleware) définit
        justement TENANT_PUBLIC comme "accessible sans authentification" —
        avant ce correctif, ce middleware-ci ignorait totalement
        TENANT_PUBLIC_ROUTES et ne connaissait que GLOBAL_PUBLIC_ROUTES.
        Conséquence concrète : un Authorization header périmé (cas très
        courant : le frontend rejoue le vieux token expiré au moment même
        où il appelle /refresh pour en obtenir un nouveau) faisait
        planter la requête en 401 "Token invalide ou expiré" AVANT
        d'atteindre la vue de refresh — cassant exactement le scénario
        que cette route existe pour gérer.
        """
        path = path.rstrip('/')

        public_routes = GLOBAL_PUBLIC_ROUTES + TENANT_PUBLIC_ROUTES

        if path in public_routes:
            return True

        return any(
            path.startswith(f"{route}/")
            for route in public_routes
        )

    def is_admin_route(self, path):
        """
        Vérifie si la route nécessite des privilèges administrateur
        Compatible avec la nouvelle structure de routes versionnées
        """
        path = path.rstrip('/')
        
        if path in ADMIN_ROUTES:
            return True
            
        return any(
            path.startswith(f"{route}/") or path.startswith(route)
            for route in ADMIN_ROUTES
        )

    def is_authenticated_route(self, path):
        """
        Vérifie si la route nécessite une authentification
        Compatible avec la nouvelle structure de routes versionnées
        """
        path = path.rstrip('/')
        
        if path in AUTHENTICATED_ROUTES:
            return True
            
        return any(
            path.startswith(f"{route}/") or path.startswith(route)
            for route in AUTHENTICATED_ROUTES
        )

    def is_api_route(self, path):
        """
        Vérifie si le chemin correspond à une route API
        Compatible avec la nouvelle structure : /api/route/vX/ ou /api/route/
        """
        return path.rstrip('/').startswith('/api')

    def is_versioned_api_route(self, path):
        """
        Vérifie spécifiquement si c'est une route API versionnée
        """
        from config.config import API_VERSIONS
        
        path = path.rstrip('/')
        return any(
            f'/{version}/' in path or path.endswith(f'/{version}')
            for version in API_VERSIONS
        )

    def get_api_version_from_path(self, path):
        """
        Extrait la version de l'API depuis le chemin
        """
        from config.config import API_VERSIONS
        
        for version in API_VERSIONS:
            if f'/{version}/' in path or path.endswith(f'/{version}'):
                return version
        return None

    def process_request(self, request):
        try:
            # Debug logging pour le développement
            if settings.DEBUG:
                logger.debug(f"[JWTMiddleware] 🔍 Processing request: {request.path}")
                logger.debug(f"[JWTMiddleware] 🔍 Is public route: {self.is_public_route(request.path)}")
                logger.debug(f"[JWTMiddleware] 🔍 Is authenticated route: {self.is_authenticated_route(request.path)}")
                logger.debug(f"[JWTMiddleware] 🔍 Is admin route: {self.is_admin_route(request.path)}")

            # Route publique = pas d'authentification requise
            if self.is_public_route(request.path):
                request.user = None
                request.auth_info = {
                    'is_authenticated': False,
                    'is_public_route': True,
                    'requires_auth': False
                }
                logger.debug(f"[Auth] 🌐 Accès à la route publique : {request.path}")
                return None

            # Extraction et validation du token JWT
            token = self._extract_token(request)
            if token:
                user = self._authenticate_with_token(token, request)
                if user is None:
                    return JsonResponse({
                        'error': 'Token invalide ou expiré.',
                        'error_code': 'INVALID_TOKEN'
                    }, status=401)
                
                request.user = user
                request.auth_info = {
                    'is_authenticated': True,
                    'user_id': user.id,
                    'username': user.username,
                    'is_staff': user.is_staff,
                    'token_provided': True
                }
                
                # Ajout des informations de version API si disponible
                api_version = self.get_api_version_from_path(request.path)
                if api_version:
                    request.auth_info['api_version'] = api_version

            else:
                request.user = None
                request.auth_info = {
                    'is_authenticated': False,
                    'token_provided': False,
                    'requires_auth': self.is_authenticated_route(request.path)
                }

            # Vérification des permissions
            return self._check_permissions(request)

        except Exception as e:
            logger.error(f"[Auth] ❌ Erreur inattendue dans le middleware JWT : {str(e)}", exc_info=True)
            
            if self.is_api_route(request.path):
                return JsonResponse({
                    'error': 'Erreur serveur lors de l\'authentification.',
                    'error_code': 'AUTH_MIDDLEWARE_ERROR'
                }, status=500)
            else:
                return JsonResponse({'error': 'Erreur serveur.'}, status=500)

    def process_response(self, request, response):
        """
        Nettoyage et ajout d'informations après traitement de la requête
        """
        # Ajout d'headers informatifs pour les réponses API
        if hasattr(request, 'auth_info') and self.is_api_route(request.path):
            if request.auth_info.get('is_authenticated'):
                response['X-User-Authenticated'] = 'true'
                response['X-User-ID'] = str(request.auth_info.get('user_id', ''))
                
                # Ajout de la version API si disponible
                api_version = request.auth_info.get('api_version')
                if api_version:
                    response['X-API-Version'] = api_version
            else:
                response['X-User-Authenticated'] = 'false'

        # Toujours repasser au schéma public après la requête
        try:
            connection.set_schema('public')
        except Exception as e:
            logger.warning(f"[Auth] Erreur lors du retour au schéma public : {str(e)}")

        return response

    def _extract_token(self, request):
        """
        Extrait le token JWT du header Authorization
        Supporte plusieurs formats d'authentification
        """
        # Bearer token dans Authorization header (standard)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            logger.debug(f"[Auth] Token extrait du header Authorization")
            return token

        # Token dans l'en-tête X-Auth-Token (alternative)
        x_auth_token = request.headers.get('X-Auth-Token')
        if x_auth_token:
            logger.debug(f"[Auth] Token extrait du header X-Auth-Token")
            return x_auth_token

        # Token dans les paramètres de requête (pour certains cas spécifiques)
        token_param = request.GET.get('token')
        if token_param:
            logger.debug(f"[Auth] Token extrait des paramètres de requête")
            return token_param

        logger.debug(f"[Auth] Aucun token trouvé dans la requête")
        return None

    def _authenticate_with_token(self, token, request):
        """
        Authentifie l'utilisateur via le token JWT
        Retourne l'utilisateur ou None si échec
        Version améliorée avec gestion des erreurs détaillée
        """
        try:
            # Validation du token via TokenService
            if not TokenService.validate_token(token, request):
                logger.warning(f"[Auth] ⚠️ Token invalide pour la requête : {request.path}")
                return None

            # Récupération de l'utilisateur associé au token
            token_obj = TokenService.get_token_from_string(token, request)
            user = token_obj.user
            
            # Vérifications supplémentaires sur l'utilisateur
            if not user.is_active:
                logger.warning(f"[Auth] ⚠️ Utilisateur inactif : {user.username}")
                return None

            logger.debug(f"[Auth] 🔐 Utilisateur authentifié : {user.username} (ID: {user.id})")
            return user

        except TokenService.TokenNotFound:
            logger.warning(f"[Auth] ⚠️ Token non associé à un utilisateur : {request.path}")
            return None
        except TokenService.TokenExpired:
            logger.warning(f"[Auth] ⚠️ Token expiré pour la requête : {request.path}")
            return None
        except Exception as e:
            logger.error(f"[Auth] ❌ Erreur lors de l'authentification : {str(e)}", exc_info=True)
            return None

    def _check_permissions(self, request):
        """
        Vérifie les permissions selon le type de route
        Version améliorée avec messages d'erreur détaillés
        """
        # Routes administrateur
        if self.is_admin_route(request.path):
            if not request.user:
                logger.warning(f"[Auth] ⚠️ Accès admin refusé - non authentifié : {request.path}")
                return JsonResponse({
                    'error': 'Authentification requise pour accéder aux ressources administrateur.',
                    'error_code': 'ADMIN_AUTH_REQUIRED'
                }, status=401)
            
            if not request.user.is_staff:
                logger.warning(f"[Auth] ⚠️ Accès admin refusé pour utilisateur : {request.user.username}")
                return JsonResponse({
                    'error': 'Privilèges administrateur requis.',
                    'error_code': 'ADMIN_PRIVILEGES_REQUIRED'
                }, status=403)
            
            logger.debug(f"[Auth] ✅ Accès admin autorisé pour : {request.user.username}")

        # Routes authentifiées
        elif self.is_authenticated_route(request.path):
            if not request.user:
                logger.warning(f"[Auth] ⚠️ Authentification requise pour : {request.path}")
                return JsonResponse({
                    'error': 'Authentification requise pour accéder à cette ressource.',
                    'error_code': 'AUTH_REQUIRED'
                }, status=401)
            
            logger.debug(f"[Auth] ✅ Accès autorisé pour utilisateur authentifié : {request.user.username}")

        # Vérification du contexte tenant pour les routes non-publiques
        if not self.is_public_route(request.path):
            tenant = getattr(request, 'tenant', None)
            if tenant is None and request.user:
                # Un utilisateur authentifié sans tenant associé n'est une
                # anomalie QUE si on est sur le schéma d'un TENANT (où un
                # tenant aurait dû être résolu par TenantMiddleware) et pas
                # sur le schéma PUBLIC. Le schéma public sans tenant est
                # l'état normal et attendu du domaine racine (admin global,
                # API de plateforme) -- ce n'est jamais une erreur, quel
                # que soit le chemin appelé. Avant ce correctif, seule une
                # liste figée de préfixes ('/admin/', '/api/tenants/',
                # '/api/health/') était tolérée : toute autre route
                # authentifiée appelée sur le domaine racine (ex :
                # /api/token/vX/settings/, réservée aux super-admins de
                # plateforme) était rejetée à tort en 400.
                if connection.schema_name != get_public_schema_name():
                    logger.warning(f"[Auth] ⚠️ Utilisateur authentifié sans contexte tenant : {request.path} (User: {request.user.username})")
                    return JsonResponse({
                        'error': 'Contexte tenant requis pour cette ressource.',
                        'error_code': 'TENANT_CONTEXT_REQUIRED'
                    }, status=400)

        return None

    def process_exception(self, request, exception):
        """
        Gestion des exceptions au niveau du middleware
        """
        logger.error(f"[Auth] Exception dans le middleware JWT : {str(exception)}", exc_info=True)
        
        # S'assurer qu'on est sur le schéma public en cas d'exception
        try:
            connection.set_schema('public')
        except Exception:
            pass

        # Laisser Django gérer l'exception normalement
        return None