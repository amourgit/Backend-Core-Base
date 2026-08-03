from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from token_manager.models import TokenManager, TokenSettings
from tenants.models import Tenant
from django_tenants.utils import schema_context
import uuid
import logging
from config.fonction import formatReponse
from rest_framework import status

logger = logging.getLogger(__name__)

class TokenService:
    """
    Service de gestion globale des tokens JWT
    """
    class TokenNotFound(Exception):
        pass

    class TenantNotFound(Exception):
        pass

    @staticmethod
    def authenticate_user(username, password, tenant_schema=None):
        """
        Authentifie un utilisateur dans un tenant spécifique
        """
        try:
            if tenant_schema:
                with schema_context(tenant_schema):
                    from django.contrib.auth import authenticate
                    user = authenticate(username=username, password=password)
                    if user:
                        return user, tenant_schema
            return None, None
        except Exception as e:
            logger.error(f"Erreur lors de l'authentification: {str(e)}")
            return None, None

    @staticmethod
    def find_user_tenant(username):
        """
        Trouve le tenant d'un utilisateur en cherchant dans tous les tenants
        """
        tenants = Tenant.objects.filter(is_active=True)
        for tenant in tenants:
            try:
                with schema_context(tenant.schema_name):
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    if User.objects.filter(username=username).exists():
                        return tenant.schema_name
            except Exception as e:
                logger.error(f"Erreur lors de la recherche dans le tenant {tenant.schema_name}: {str(e)}")
                continue
        return None

    @staticmethod
    def generate_tokens(user, token_settings, request=None, tenant_schema=None):
        """
        Génère une paire de tokens (access + refresh) pour un utilisateur
        """
        try:
            # # Récupérer les paramètres de token globaux
            # token_settings = TokenSettings.get_active_settings()
            
            # if not token_settings:
            #     # Si pas de configuration, créer une configuration par défaut
            #     token_settings = TokenSettings.objects.create(
            #         name="Configuration par défaut - Global",
            #         access_token_lifetime=5,  # 5 minutes
            #         refresh_token_lifetime=1440,  # 24 heures
            #         max_tokens_per_user=5,
            #         rotate_refresh_tokens=True,
            #         blacklist_after_rotation=True,
            #         cookie_secure=True,
            #         cookie_samesite='Lax',
            #         enable_blacklist=True,
            #         blacklist_cleanup_after=60,
            #         require_https=True,
            #         validate_ip=True,
            #         validate_user_agent=True,
            #         is_active=True
            #     )

            # Vérifier le nombre maximum de tokens
            active_tokens = TokenManager.objects.filter(
                user=user,
                is_revoked=False,
                expires_at__gt=timezone.now()
            ).count()

            if active_tokens >= token_settings.max_tokens_per_user:
                # Révoquer le plus ancien token
                oldest_token = TokenManager.objects.filter(
                    user=user,
                    is_revoked=False
                ).order_by('created_at').first()
                if oldest_token:
                    oldest_token.revoke()

            # Générer les tokens
            refresh = RefreshToken.for_user(user)
            
            # Ajouter le tenant_schema au token
            if tenant_schema:
                refresh['tenant_schema'] = tenant_schema
            
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            # Créer l'entrée dans TokenManager
            token = TokenManager.objects.create(
                user=user,
                tenant_id=tenant_schema,
                jti=uuid.UUID(refresh['jti']),
                access_token=access_token,
                refresh_token=refresh_token,
                ip_address=request.META.get('REMOTE_ADDR') if request else None,
                user_agent=request.META.get('HTTP_USER_AGENT') if request else None,
                expires_at=timezone.now() + token_settings.to_jwt_settings()['ACCESS_TOKEN_LIFETIME']
            )

            return {
                'access': access_token,
                'refresh': refresh_token,
                'jti': str(token.jti),
                'tenant_schema': tenant_schema
            }

        except Exception as e:
            logger.error(f"Erreur lors de la génération des tokens: {str(e)}")
            raise

    @staticmethod
    def get_token_by_access_token(access_token):
        """
        Récupère un token par son access_token
        """
        return TokenManager.objects.filter(access_token=access_token).first()
    
    @staticmethod
    def get_token_by_choice_data(data):
        """
        Récupère un token par tous les champs choisis
        """
        formatReponse['type'] = 'error'
        formatReponse['titre'] = 'Informations Erronees'
        formatReponse['niveau'] = 100
        formatReponse['message'] = "Le refresh_token n'existe pas ou a deja ete utilise, veuillez vous reconnecter"
        formatReponse['status'] = int(401)
        token = None
        try:
            token = TokenManager.objects.filter(**data).first()
        except TokenManager.DoesNotExist:
            return token, formatReponse
        return token, formatReponse

    @staticmethod
    def get_all_token_by_perform(data, is_unique=True):
        """
        Récupère tous les tokens d'un utilisateur
        """
        if is_unique:
            return TokenManager.objects.filter(**data).first()
        else:
            return TokenManager.objects.filter(**data).all()

    @staticmethod
    def update_all_token_by_perform(data_get, data_update):
        return TokenManager.objects.filter(**data_get).all().update(**data_update)
    
    @staticmethod
    def update_token_by_perform(data_get, data_update):
        return TokenManager.objects.filter(**data_get).update(**data_update)

    @staticmethod
    def delete_token_by_perform(data_get):
        return TokenManager.objects.filter(**data_get).delete()

    @staticmethod
    def create_token(data):
        """
        Crée un token
        """
        return TokenManager.objects.create(
            **data
        )

    @staticmethod
    def validate_token(token_string, request=None):
        """
        Valide un token et vérifie sa conformité avec les paramètres
        """
        try:
            # Récupérer les paramètres de token globaux
            token_settings = TokenSettings.get_active_settings()
            
            if not token_settings:
                # Si pas de configuration, créer une configuration par défaut
                token_settings = TokenSettings.objects.create(
                    name="Configuration par défaut - Global",
                    access_token_lifetime=5,
                    refresh_token_lifetime=1440,
                    max_tokens_per_user=5,
                    rotate_refresh_tokens=True,
                    blacklist_after_rotation=True,
                    cookie_secure=True,
                    cookie_samesite='Lax',
                    enable_blacklist=True,
                    blacklist_cleanup_after=60,
                    require_https=True,
                    validate_ip=True,
                    validate_user_agent=True,
                    is_active=True
                )

            # Vérifier le token dans la base de données
            token = TokenManager.objects.filter(
                access_token=token_string,
                is_revoked=False
            ).first()

            if not token or not token.is_valid():
                return False

            # Vérifications supplémentaires selon les paramètres
            if token_settings.validate_ip and request:
                if token.ip_address != request.META.get('REMOTE_ADDR'):
                    return False

            if token_settings.validate_user_agent and request:
                if token.user_agent != request.META.get('HTTP_USER_AGENT'):
                    return False

            # Mettre à jour la dernière utilisation
            token.update_last_used()
            return True

        except Exception as e:
            logger.error(f"Erreur lors de la validation du token: {str(e)}")
            return False

    @staticmethod
    def get_token_from_string(token_string, request=None):
        """
        Récupère l'objet TokenManager à partir d'une chaîne de token
        """
        token = TokenManager.objects.filter(
            access_token=token_string,
            is_revoked=False
        ).first()

        if not token or not token.is_valid():
            raise TokenService.TokenNotFound("Token invalide ou expiré")

        return token

    @staticmethod
    def get_token_from_header(request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = auth_header.split(' ')[1]  if auth_header.startswith('Bearer ') else None
        return token

    @staticmethod
    def revoke_token(token_string, request=None):
        """
        Révoque un token
        """
        try:
            token = TokenService.get_token_from_string(token_string, request)
            token.revoke()
            return True
        except TokenService.TokenNotFound:
            return False

    @staticmethod
    def cleanup_expired_tokens():
        """
        Marque comme révoqués tous les tokens expirés.
        """
        now = timezone.now()
        TokenManager.objects.filter(
            expires_at__lt=now,
            is_revoked=False
        ).update(
            is_revoked=True,
            revoked_at=now
        )

    @staticmethod
    def revoke_all_user_tokens(user):
        """
        Révoque tous les tokens d'un utilisateur
        """
        TokenManager.objects.filter(
            user=user,
            is_revoked=False
        ).update(
            is_revoked=True,
            revoked_at=timezone.now()
        )

    @staticmethod
    def cleanup_expired_tokens():
        """
        Nettoie les tokens expirés
        """
        TokenManager.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()

    @staticmethod
    def cleanup_revoked_tokens():
        """
        Nettoie les tokens révoqués selon la durée de conservation
        """
        token_settings = TokenSettings.get_active_settings()
        
        if not token_settings or not token_settings.enable_blacklist:
            return

        cleanup_after = token_settings.blacklist_cleanup_after
        TokenManager.objects.filter(
            is_revoked=True,
            revoked_at__lt=timezone.now() - timezone.timedelta(minutes=cleanup_after)
        ).delete() 