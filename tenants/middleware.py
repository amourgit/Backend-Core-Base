from django.db import connection
from django_tenants.middleware.main import TenantMainMiddleware
from tenants.models import Tenant
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from config.config import (
    GLOBAL_PUBLIC_ROUTES, 
    TENANT_PUBLIC_ROUTES, 
    AUTHENTICATED_ROUTES, 
    ADMIN_ROUTES,
    API_VERSIONS
)
from config.fonction import resolve_request_hostname
import re
import logging

logger = logging.getLogger(__name__)


class TenantMiddleware(TenantMainMiddleware):
    """
    Middleware responsable de la résolution des tenants et du routage selon les règles définies.
    
    Gère 4 types de routes :
    - GLOBAL_PUBLIC : accessibles sans tenant (schéma public)
    - TENANT_PUBLIC : accessibles sans auth mais nécessitent un tenant
    - AUTHENTICATED : nécessitent tenant + authentification  
    - ADMIN : routes administrateur (tenant optionnel selon la route)
    """
    
    # Configuration centralisée des types de routes
    ROUTE_TYPES = {
        "GLOBAL_PUBLIC": GLOBAL_PUBLIC_ROUTES,
        "TENANT_PUBLIC": TENANT_PUBLIC_ROUTES,
        "AUTHENTICATED": AUTHENTICATED_ROUTES,
        "ADMIN": ADMIN_ROUTES,
    }
    
    # Configuration pour les routes admin nécessitant un tenant
    ADMIN_TENANT_REQUIRED_ROUTES = [
        '/api/admin/v1/tenant-settings',
        '/api/admin/v2/tenant-settings',
        # Ajouter d'autres routes admin spécifiques au tenant
    ]

    # Apps dont les tables n'existent QUE dans les schémas tenant, JAMAIS
    # dans le schéma public -- dérivé directement de
    # config/settings.py:TENANT_APPS - SHARED_APPS (pas une liste blanche
    # à maintenir séparément, c'est la source de vérité qui déciderait
    # elle-même si une migration echouerait sur le schéma public).
    #
    # 'token', 'domain', 'tenants' sont SHARED_APPS uniquement (table
    # accessible peu importe le schema actif). 'users' et 'referentiels'
    # sont doublés (SHARED_APPS ET TENANT_APPS, volontairement -- voir le
    # commentaire sur SHARED_APPS dans config/settings.py) : la table
    # EXISTE dans le schéma public, mais contient un jeu de données
    # DIFFÉRENT (les comptes de la plateforme, pas ceux du tenant) --
    # risque résiduel de confusion si un token émis pour un tenant est
    # utilisé sur le domaine racine, mais pas de crash SQL, donc non
    # bloqué ici (voir discussion complète dans le message de commit).
    #
    # Utilisé pour les routes TENANT_PUBLIC ET AUTHENTICATED accédées
    # depuis le domaine racine : sans vrai tenant positionné par ce
    # middleware, une requête vers l'une de ces apps plante en 500 dès
    # la première requête SQL (ex: relation "news_news" does not
    # exist), au lieu d'un 400 clair et exploitable.
    TENANT_ONLY_APPS = (
        'news', 'commentaires', 'sondages', 'liens',
        'notifications', 'journal', 'moderation', 'statistiques',
    )

    def get_hostname_from_request(self, request):
        """
        Extrait le hostname de la requête -- résolution centralisée,
        partagée avec DomainService.get_sous_domaine_by_request (voir
        config/fonction.py:resolve_request_hostname). En-tête
        X-Tenant-Domain prioritaire sur le Host HTTP standard : utile
        quand frontend et backend ne partagent pas la même origine
        (ports distincts en dev), le Host vu par Django n'étant alors
        pas forcément celui affiché dans la barre d'adresse du
        navigateur.
        """
        return resolve_request_hostname(request)

    def is_valid_domain(self, hostname):
        """
        Vérifie si le domaine est valide. Deux cas légitimes :
          1. Le domaine racine lui-même (ex: "localhost") -> schéma public,
             utilisé pour l'admin GLOBAL de la plateforme.
          2. Un sous-domaine de tenant (ex: "ecole1.localhost") -> schéma du
             tenant, utilisé pour l'admin/API de cet établissement.

        Avant ce correctif, seul le cas 2 était accepté : toute requête sur
        le domaine racine (donc l'admin global) était rejetée en 404 avant
        même d'atteindre Django.
        """
        if not settings.MAIN_DOMAIN:
            logger.error("MAIN_DOMAIN n'est pas configuré dans les paramètres")
            return False

        # Cas 1 : domaine racine / plateforme (schéma public)
        if hostname == settings.MAIN_DOMAIN.lower():
            return True

        # Cas 2 : sous-domaine de tenant
        pattern = rf'^[a-zA-Z0-9-]+\.{re.escape(settings.MAIN_DOMAIN)}$'
        return bool(re.match(pattern, hostname))

    def get_route_type(self, path):
        """
        Détermine le type de route de manière centralisée
        Retourne le type de route ou None si non classée
        """
        path = path.rstrip('/')
        
        # Vérifier d'abord les routes admin.
        # IMPORTANT : path a déjà perdu son slash final ci-dessus, donc
        # "/admin/" est devenu "/admin". Comparer avec startswith('/admin/')
        # ne matche alors JAMAIS la racine du site admin lui-même (seulement
        # ses sous-pages comme "/admin/login"), et /admin/ finissait donc en
        # 404 "Type de route non géré" au lieu d'ouvrir le tableau de bord.
        if path == '/admin' or path.startswith('/admin/'):
            return 'ADMIN'
        
        # Vérifier les autres types de routes.
        #
        # IMPORTANT : on ne retourne PAS sur la première catégorie qui
        # matche (ce que faisait l'ancienne implémentation, dans l'ordre
        # d'itération GLOBAL_PUBLIC -> TENANT_PUBLIC -> AUTHENTICATED ->
        # ADMIN). Une entrée "nue" comme ('token', None) dans TENANT_PUBLIC
        # génère '/api/token/vX', et startswith('/api/token/vX/') matche
        # AUSSI '/api/token/vX/logout' -- alors même que 'logout' est
        # explicitement (et plus précisément) classé AUTHENTICATED juste
        # après dans config.py. Avec l'ancien "premier match gagne",
        # TENANT_PUBLIC étant vérifié en premier, 'logout' était donc
        # TOUJOURS classé TENANT_PUBLIC, jamais AUTHENTICATED -- rendant
        # la classification plus précise totalement inopérante, quel que
        # soit l'ordre des entrées dans les listes de config.py.
        #
        # On choisit maintenant la correspondance la PLUS SPÉCIFIQUE
        # (la route enregistrée la plus longue) tous types confondus :
        # '/api/token/vX/logout' (21 caractères, AUTHENTICATED) l'emporte
        # sur '/api/token/vX' (14 caractères, TENANT_PUBLIC). Deux routes
        # de même longueur ne peuvent pas exister ensemble (une seule
        # chaîne possible), donc pas d'ambiguïté possible.
        meilleur_type, meilleure_longueur = None, -1
        for route_type, routes in self.ROUTE_TYPES.items():
            for route in routes:
                if path == route:
                    longueur = len(route)
                elif path.startswith(f"{route}/"):
                    longueur = len(route)
                else:
                    continue
                if longueur > meilleure_longueur:
                    meilleure_longueur, meilleur_type = longueur, route_type

        return meilleur_type

    def is_api_route(self, path):
        """Vérifie si le chemin correspond à une route API ou admin"""
        path = path.rstrip('/')
        return path.startswith('/api') or path.startswith('/admin')

    def is_versioned_api_route(self, path):
        """Vérifie spécifiquement si c'est une route API versionnée"""
        path = path.rstrip('/')
        return any(
            f'/{version}/' in path or path.endswith(f'/{version}')
            for version in API_VERSIONS
        )

    def get_api_version_from_path(self, path):
        """Extrait la version de l'API depuis le chemin"""
        for version in API_VERSIONS:
            if f'/{version}/' in path or path.endswith(f'/{version}'):
                return version
        return None

    def admin_route_requires_tenant(self, path):
        """
        Vérifie si une route admin nécessite un tenant spécifique
        """
        path = path.rstrip('/')
        return any(
            path == route or path.startswith(f"{route}/")
            for route in self.ADMIN_TENANT_REQUIRED_ROUTES
        )

    def _set_request_tenant(self, request, tenant, hostname):
        """
        Méthode utilitaire pour configurer le tenant sur la requête
        """
        request.tenant = tenant
        connection.set_tenant(tenant)
        request.tenant_info = {
            'name': tenant.name,
            'schema_name': tenant.schema_name,
            'domain': hostname,
            'is_active': tenant.is_active
        }

    def _resolve_tenant_with_cache(self, hostname):
        """
        Résout le tenant avec mise en cache pour optimiser les performances
        Cache TTL: 5 minutes
        """
        cache_key = f"tenant_resolution:{hostname}"
        tenant = cache.get(cache_key)
        
        if tenant is not None:
            # Cache hit - tenant peut être un objet Tenant ou False (pas trouvé)
            logger.debug(f"[MultiTenant] Cache hit pour {hostname} -> {tenant}")
            return tenant if tenant else None
        
        # Cache miss - résolution depuis la DB
        tenant = self._resolve_tenant(hostname)
        
        # Mettre en cache (tenant ou False si non trouvé)
        cache_value = tenant if tenant else False
        cache.set(cache_key, cache_value, timeout=300)  # 5 minutes
        
        return tenant

    def _resolve_tenant(self, hostname):
        """
        Résout le tenant en essayant d'abord par domaine complet, puis par sous-domaine
        Optimisation : pas de select_related inutile
        """
        try:
            # Essayer d'abord par le domaine complet
            tenant = Tenant.objects.get(domains__domain=hostname)
            logger.debug(f"[MultiTenant] Tenant trouvé par domaine complet : {hostname} -> {tenant.name}")
            return tenant
        except Tenant.DoesNotExist:
            try:
                # Si non trouvé, essayer par le sous-domaine
                sous_domaine = hostname.split('.')[0]
                tenant = Tenant.objects.get(sous_domaine=sous_domaine)
                logger.debug(f"[MultiTenant] Tenant trouvé par sous-domaine : {sous_domaine} -> {tenant.name}")
                return tenant
            except Tenant.DoesNotExist:
                logger.warning(f"[MultiTenant] Aucun tenant trouvé pour : {hostname} (sous-domaine: {sous_domaine})")
                return None
            except Exception as e:
                logger.error(f"[MultiTenant] Erreur lors de la résolution par sous-domaine : {str(e)}")
                return None
        except Exception as e:
            logger.error(f"[MultiTenant] Erreur lors de la résolution par domaine complet : {str(e)}")
            return None

    def _handle_error_response(self, request, message, error_code, status_code):
        """
        Centralise la gestion des réponses d'erreur
        """
        if self.is_api_route(request.path):
            return JsonResponse({
                "detail": message,
                "error_code": error_code
            }, status=status_code)
        else:
            return HttpResponse(message, status=status_code, content_type="text/plain")

    def is_root_domain(self, hostname):
        """
        Vrai si la requête cible le domaine racine (ex: "localhost"), c'est
        à dire la plateforme elle-même, PAS un établissement particulier.
        """
        return hostname == settings.MAIN_DOMAIN.lower()

    def _get_app_prefix_from_path(self, path):
        """
        Extrait <app> depuis un chemin '/api/<app>/vX/...'. Retourne None
        si le chemin ne suit pas ce schéma (ne devrait pas arriver pour
        une route déjà classée TENANT_PUBLIC/AUTHENTICATED par
        get_route_type(), mais on reste défensif).
        """
        parts = path.strip('/').split('/')
        if len(parts) >= 2 and parts[0] == 'api':
            return parts[1]
        return None

    def _set_request_public(self, request, hostname):
        """
        Configure la requête pour le contexte PUBLIC (plateforme) : PAS de
        Tenant associé. On ne fait PAS `request.tenant = None` : voir le
        commentaire détaillé dans process_request (branche GLOBAL_PUBLIC) --
        django_tenants teste `hasattr(request, 'tenant')`, pas sa valeur.
        request.tenant_info reste renseigné pour l'info/debug (headers de
        réponse), lui n'a pas ce piège.
        """
        request.tenant_info = {
            'name': 'Plateforme',
            'schema_name': connection.schema_name,
            'domain': hostname,
            'is_active': True,
        }

    def process_request(self, request):
        try:
            # Les requêtes OPTIONS (preflight CORS) ne doivent JAMAIS être
            # soumises à la validation de route/tenant ci-dessous : c'est
            # CorsMiddleware (plus bas dans MIDDLEWARE, voir
            # config/settings.py) qui doit y répondre, avec les en-têtes
            # Access-Control-*. Ce middleware étant placé AVANT
            # CorsMiddleware dans la pile (obligatoire : il doit pouvoir
            # positionner le schema PostgreSQL avant que quoi que ce soit
            # d'autre ne s'exécute), le laisser bloquer un preflight avec
            # une erreur 400/404 (ex: tenant inexistant) priverait CETTE
            # réponse des en-têtes CORS -- le navigateur ne verrait alors
            # qu'une erreur CORS opaque et générique, jamais le message
            # clair que la vraie requête aurait reçu.
            if request.method == "OPTIONS":
                return None

            # Debug logging pour le développement
            if settings.DEBUG:
                route_type = self.get_route_type(request.path)
                logger.debug(f"[TenantMiddleware] 🔍 Processing request: {request.path}")
                logger.debug(f"[TenantMiddleware] 🔍 Route type: {route_type}")
                if self.is_versioned_api_route(request.path):
                    version = self.get_api_version_from_path(request.path)
                    logger.debug(f"[TenantMiddleware] 🔍 API Version: {version}")

            # Détermination du type de route
            route_type = self.get_route_type(request.path)
            
            # 1. GLOBAL_PUBLIC : pas de résolution tenant, toujours schéma public.
            #    IMPORTANT : on ne met PAS request.tenant = None ici. Les
            #    templates admin fournis par django_tenants (chargés
            #    automatiquement car l'app est dans INSTALLED_APPS) testent
            #    `hasattr(request, 'tenant')` pour savoir si un VRAI tenant a
            #    été résolu ; si l'attribut existe mais vaut None, ils
            #    plantent en tentant request.tenant.schema_name. Ne pas
            #    définir l'attribut du tout est le contrat attendu par
            #    django_tenants pour "pas de tenant" -- et c'est équivalent
            #    pour notre propre code, qui lit toujours via
            #    getattr(request, 'tenant', None).
            if route_type == "GLOBAL_PUBLIC":
                connection.set_schema_to_public()
                logger.debug(f"[MultiTenant] 🌐 Route GLOBAL_PUBLIC : {request.path}")
                return None

            # Pour toutes les autres routes (y compris ADMIN), on doit
            # d'abord savoir si on est sur le domaine racine ou un
            # sous-domaine de tenant.
            hostname = self.get_hostname_from_request(request)
            
            if not self.is_valid_domain(hostname):
                return self._handle_error_response(
                    request, 
                    "Domaine ou tenant introuvable.", 
                    "INVALID_DOMAIN", 
                    404
                )

            # 2. DOMAINE RACINE = SCHÉMA PUBLIC, PAR DÉFINITION.
            #    Règle explicite, volontairement sans aucune recherche en
            #    base : le domaine racine EST la plateforme (schéma
            #    public), il n'y a pas de "Tenant" à trouver pour lui.
            #    Avant ce correctif, on appelait quand même
            #    _resolve_tenant_with_cache(hostname) ici, ce qui exigeait
            #    qu'une ligne Tenant(schema_name='public') + Domain(domain=
            #    MAIN_DOMAIN) existe en base (créée par
            #    `manage.py bootstrap_public`). Si cette ligne n'existait
            #    pas encore -- DB fraîchement recréée, oubli de la
            #    commande, etc. -- absolument TOUTE requête sur le domaine
            #    racine échouait en 404 "Domaine ou tenant introuvable"
            #    (TENANT_NOT_FOUND), y compris /admin/ lui-même. C'est
            #    incohérent : le schéma public existe toujours (c'est le
            #    schéma par défaut de PostgreSQL), sa disponibilité ne doit
            #    jamais dépendre d'une ligne de données.
            if self.is_root_domain(hostname):
                connection.set_schema_to_public()
                self._set_request_public(request, hostname)
                logger.debug(f"[MultiTenant] 🏛️ Domaine racine -> schéma public : {request.path}")

                if route_type == "ADMIN":
                    return None

                if route_type in ("TENANT_PUBLIC", "AUTHENTICATED"):
                    app_prefix = self._get_app_prefix_from_path(request.path)
                    if app_prefix not in self.TENANT_ONLY_APPS:
                        return None

                    # Ex: /api/news/v1/news/ (TENANT_PUBLIC) ou
                    # /api/notifications/v1/notifications/ (AUTHENTICATED)
                    # appelée sur "localhost" au lieu de
                    # "moncampus.localhost" -- la vue va planter en 500
                    # (relation "news_news" does not exist : cette table
                    # n'existe que dans les schémas tenant). On coupe court
                    # avec une erreur explicite, exploitable par le client,
                    # plutôt que de laisser remonter une ProgrammingError
                    # psycopg2 brute.
                    logger.warning(
                        f"[MultiTenant] ⚠️ Route nécessitant un tenant réel "
                        f"appelée sur le domaine racine : {request.path}"
                    )
                    return self._handle_error_response(
                        request,
                        "Cette ressource appartient à un établissement précis et doit être "
                        "appelée depuis son sous-domaine (ex: moncampus.{}), pas depuis le "
                        "domaine racine.".format(settings.MAIN_DOMAIN),
                        "TENANT_REQUIRED",
                        400
                    )

                logger.warning(f"[MultiTenant] ⚠️ Type de route non géré : {route_type} pour {request.path}")
                return self._handle_error_response(
                    request,
                    "Type de route non géré.",
                    "UNHANDLED_ROUTE_TYPE",
                    404
                )

            # 3. Sous-domaine d'un établissement précis : là, et seulement
            #    là, on résout un vrai Tenant en base.
            connection.set_schema_to_public()
            tenant = self._resolve_tenant_with_cache(hostname)
            
            if not tenant:
                return self._handle_error_response(
                    request, 
                    "Domaine ou tenant introuvable.", 
                    "TENANT_NOT_FOUND", 
                    404
                )

            # Configuration du tenant pour la requête
            self._set_request_tenant(request, tenant, hostname)
            logger.debug(f"[MultiTenant] 🌐 Tenant résolu : {tenant.name} pour {request.path}")
            
            # Pour les routes admin, on s'assure que le tenant est valide
            if route_type == "ADMIN":
                if not tenant.is_active:
                    return self._handle_error_response(
                        request,
                        "Ce tenant est désactivé.",
                        "TENANT_INACTIVE",
                        403
                    )
                logger.debug(f"[MultiTenant] 👑 Accès admin avec tenant : {tenant.name}")
                return None
                
            # Pour les autres types de routes (TENANT_PUBLIC, AUTHENTICATED)
            return self._handle_tenant_route(request, route_type, tenant, hostname)

        except Exception as e:
            logger.error(f"[MultiTenant] ❌ Erreur inattendue : {str(e)}", exc_info=True)
            return self._handle_error_response(
                request, 
                "Erreur serveur lors de la résolution du tenant.", 
                "TENANT_RESOLUTION_ERROR", 
                500
            )

    def _handle_tenant_route(self, request, route_type, tenant, hostname):
        """
        Gère les routes nécessitant un tenant
        """
        # Configuration du tenant pour la requête
        self._set_request_tenant(request, tenant, hostname)
        
        if route_type == "TENANT_PUBLIC":
            logger.debug(f"[MultiTenant] 🌐 Route TENANT_PUBLIC : {request.path} | Tenant: {tenant.name}")
            return None

        if route_type == "AUTHENTICATED":
            logger.debug(f"[MultiTenant] 🔐 Route AUTHENTICATED : {request.path} | Tenant: {tenant.name}")
            return None
            
        # Si on arrive ici, la route n'est pas gérée (normalement ne devrait pas arriver)
        logger.warning(f"[MultiTenant] ⚠️ Type de route non géré : {route_type} pour {request.path}")
        return self._handle_error_response(
            request,
            "Type de route non géré.",
            "UNHANDLED_ROUTE_TYPE",
            404
        )

    def process_response(self, request, response):
        """
        Nettoyage et finalisation après traitement de la requête
        """
        # Ajout d'headers informatifs pour les API (sécurisé selon l'environnement)
        if hasattr(request, 'tenant') and request.tenant:
            if self.is_api_route(request.path):
                if settings.DEBUG:
                    # En développement : headers complets pour debug
                    response['X-Tenant-Name'] = request.tenant.name
                    response['X-Tenant-Schema'] = request.tenant.schema_name
                else:
                    # En production : seulement le nom (pas d'info sensible sur la DB)
                    response['X-Tenant-Name'] = request.tenant.name
                
                # Version API disponible en dev et prod
                api_version = self.get_api_version_from_path(request.path)
                if api_version:
                    response['X-API-Version'] = api_version

        # Toujours s'assurer qu'on termine sur le schéma public
        try:
            connection.set_schema_to_public()
        except Exception as e:
            logger.warning(f"[MultiTenant] Erreur lors du retour au schéma public : {str(e)}")

        return response

    def process_exception(self, request, exception):
        """
        Gestion des exceptions au niveau du middleware
        """
        logger.error(f"[MultiTenant] Exception dans le middleware : {str(exception)}", exc_info=True)
        
        # S'assurer qu'on est sur le schéma public en cas d'exception
        try:
            connection.set_schema_to_public()
        except Exception:
            pass

        # Laisser Django gérer l'exception normalement
        return None