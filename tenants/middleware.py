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
from config.fonction import (
    resolve_request_hostname,
    get_host_header_hostname,
    get_tenant_header_hostname,
)
import re
import logging

logger = logging.getLogger(__name__)


class TenantMismatch(Exception):
    """
    Levée quand le sous-domaine (Host) ET l'en-tête X-Tenant-Domain sont
    TOUS LES DEUX présents dans une même requête mais désignent deux
    tenants DIFFÉRENTS -- voir TenantMiddleware._resolve_tenant_dual.
    Ambiguïté volontairement jamais résolue en silence (on ne choisit
    pas arbitrairement l'une des deux sources).
    """

    def __init__(self, host_hostname, tenant_from_host, header_hostname, tenant_from_header):
        self.host_hostname = host_hostname
        self.tenant_from_host = tenant_from_host
        self.header_hostname = header_hostname
        self.tenant_from_header = tenant_from_header
        super().__init__(
            f"Le sous-domaine ('{host_hostname}' -> tenant '{tenant_from_host.schema_name}') et "
            f"l'en-tête X-Tenant-Domain ('{header_hostname}' -> tenant '{tenant_from_header.schema_name}') "
            f"désignent deux tenants différents pour la même requête."
        )


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
        Vérifie que le hostname appartient au domaine principal de la plateforme.

        Règles :

        1. MAIN_DOMAIN exact
            -> domaine principal de la plateforme
            -> schéma public
            -> aucun tenant

        2. <tenant>.MAIN_DOMAIN
            -> sous-domaine tenant
            -> résolution du tenant en base

        3. Domaine explicitement enregistré (table Domain), même hors du
           schéma MAIN_DOMAIN
            -> nécessaire dès que le frontend d'un tenant n'est PAS hébergé
               en sous-domaine du backend (ex: frontend sur Vercel --
               "civitasnews.vercel.app" -- backend sur Render --
               MAIN_DOMAIN="civitasnews-backend.onrender.com" : deux
               domaines sans aucune relation de sous-domaine entre eux).
               Le frontend pose alors ce hostname dans X-Tenant-Domain
               (voir resolve_request_hostname), qui ne peut PAR
               CONSTRUCTION jamais matcher le motif "<x>.MAIN_DOMAIN" du
               cas 2. Sans ce cas 3, TOUTE requête authentifiée/tenant
               échouerait en 404 INVALID_DOMAIN dès que frontend et
               backend sont sur des domaines indépendants -- ce qui est
               le cas de tout déploiement gratuit Vercel + Render.
            -> pas moins sûr que les cas 1/2 : Domain.domain est unique en
               base et n'est peuplé QUE par un administrateur (bootstrap_tenant
               --extra-domain, ou l'admin Django) -- jamais depuis une
               requête entrante.

        4. Tout autre hostname
            -> domaine invalide
            -> 404
        """
        if not settings.MAIN_DOMAIN:
            logger.error(
                "[MultiTenant] MAIN_DOMAIN n'est pas configuré dans les paramètres"
            )
            return False

        hostname = hostname.lower().strip().rstrip(".")
        main_domain = settings.MAIN_DOMAIN.lower().strip().rstrip(".")

        # ---------------------------------------------------------
        # 1. Domaine principal de la plateforme
        # ---------------------------------------------------------
        if hostname == main_domain:
            return True

        # ---------------------------------------------------------
        # 2. Sous-domaine direct = tenant
        #
        # Exemple :
        #   MAIN_DOMAIN = civitasnews-backend.onrender.com
        #
        #   civitas.civitasnews-backend.onrender.com -> OK
        #   foo.civitasnews-backend.onrender.com     -> OK
        #
        # Mais :
        #   foo.bar.civitasnews-backend.onrender.com -> NON
        # ---------------------------------------------------------
        pattern = rf'^[a-zA-Z0-9-]+\.{re.escape(main_domain)}$'

        if re.match(pattern, hostname):
            return True

        # ---------------------------------------------------------
        # 3. Domaine explicitement enregistré (voir docstring ci-dessus)
        # ---------------------------------------------------------
        from domain.models import Domain

        if Domain.objects.filter(domain=hostname).exists():
            return True

        # ---------------------------------------------------------
        # 4. Domaine extérieur / invalide
        # ---------------------------------------------------------
        logger.warning(
            f"[MultiTenant] Domaine invalide : {hostname} "
            f"(MAIN_DOMAIN={main_domain})"
        )

        return False

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

    def _resolve_tenant_dual(self, request):
        """
        Résout le tenant en tentant les DEUX sources EN PARALLÈLE --
        sous-domaine (Host) ET en-tête X-Tenant-Domain -- au lieu de
        l'ancienne priorité stricte "en-tête sinon Host" (qui ne
        regardait qu'UNE seule source, choisie avant même de savoir si
        elle résolvait quoi que ce soit).

        Pourquoi : Render (plan gratuit) ne fournit pas de certificat TLS
        valide pour les sous-domaines de *.onrender.com (uniquement pour
        le domaine exact du service) -- en pratique, le Host vu par
        Django y est donc TOUJOURS le domaine racine du service, même
        pour une requête destinée à un tenant précis. Seul l'en-tête
        porte alors la véritable intention. À l'inverse, en dev local
        (ou le jour où un vrai domaine wildcard est configuré), c'est le
        sous-domaine qui est fiable et l'en-tête peut être absent. On ne
        privilégie donc plus une source par défaut : les deux sont
        tentées, chacune indépendamment suffisante.

        Règles :
          - un seul candidat résout un tenant -> celui-là, ça ne bloque
            jamais la suite ;
          - les deux résolvent un tenant -> DOIVENT être le MÊME tenant,
            sinon TenantMismatch (traduit en 400 par process_request) ;
          - aucun des deux ne résout de tenant -> (None, None) : à
            process_request de retomber sur la logique racine/domaine
            invalide historique.

        Le domaine racine (MAIN_DOMAIN exact) n'est jamais soumis à
        résolution ici : il ne représente aucun tenant réel, une requête
        avec Host=MAIN_DOMAIN est le cas normal de toute requête API sur
        ce déploiement (un seul domaine backend), pas une tentative de
        cibler un tenant nommé "MAIN_DOMAIN".

        Retourne (tenant, host_hostname, header_hostname, hostname_affiche).
        `tenant` est None si aucune source n'a résolu de tenant réel ;
        `hostname_affiche` est alors le meilleur candidat pour les logs
        d'erreur (en-tête si présent, sinon Host).
        """
        main_domain = (settings.MAIN_DOMAIN or '').lower()
        host_hostname = get_host_header_hostname(request)
        header_hostname = get_tenant_header_hostname(request)

        tenant_from_host = None
        if host_hostname and host_hostname != main_domain:
            tenant_from_host = self._resolve_tenant_with_cache(host_hostname)

        tenant_from_header = None
        if header_hostname and header_hostname != main_domain:
            tenant_from_header = self._resolve_tenant_with_cache(header_hostname)

        if tenant_from_host and tenant_from_header:
            if tenant_from_host.pk != tenant_from_header.pk:
                raise TenantMismatch(host_hostname, tenant_from_host, header_hostname, tenant_from_header)
            # Les deux concordent : l'en-tête l'emporte pour l'affichage,
            # par convention (voir resolve_request_hostname).
            return tenant_from_host, host_hostname, header_hostname, header_hostname

        if tenant_from_header:
            return tenant_from_header, host_hostname, header_hostname, header_hostname
        if tenant_from_host:
            return tenant_from_host, host_hostname, header_hostname, host_hostname

        return None, host_hostname, header_hostname, (header_hostname or host_hostname)

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
        Sûr face à un hostname vide (source absente, ex: en-tête
        X-Tenant-Domain non fourni) ou un MAIN_DOMAIN non configuré.
        """
        if not settings.MAIN_DOMAIN or not hostname:
            return False
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

            # Les fichiers statiques et médias ne doivent jamais être
            # soumis à la résolution des tenants. Ils sont servis
            # directement par WhiteNoise / Django.
            if request.path.startswith('/static/') or request.path.startswith('/media/'):
                return None

            # Les requêtes OPTIONS (preflight CORS) ne doivent JAMAIS être
            # soumises à la validation de route/tenant ci-dessous.
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

            # Pour toutes les autres routes (y compris ADMIN), on résout
            # le tenant en tentant les DEUX sources en parallèle -- voir
            # _resolve_tenant_dual pour le détail des règles (un seul
            # candidat suffit, les deux doivent concorder s'ils sont
            # tous les deux présents).
            try:
                tenant, host_hostname, header_hostname, hostname = self._resolve_tenant_dual(request)
            except TenantMismatch as exc:
                logger.warning(f"[MultiTenant] ⚠️ {exc}")
                return self._handle_error_response(request, str(exc), "TENANT_MISMATCH", 400)

            if tenant is not None:
                # 3. Tenant résolu (sous-domaine et/ou en-tête X-Tenant-Domain).
                connection.set_schema_to_public()
                self._set_request_tenant(request, tenant, hostname)
                logger.debug(f"[MultiTenant] 🌐 Tenant résolu : {tenant.name} pour {request.path}")

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

                return self._handle_tenant_route(request, route_type, tenant, hostname)

            # Ni le sous-domaine ni l'en-tête n'ont résolu de tenant réel.
            # On retombe sur le cas racine si L'UNE des deux sources est
            # le domaine principal -- l'autre, absente ou parasite, ne
            # doit jamais bloquer l'accès à la plateforme (même principe
            # que ci-dessus : une seule source suffisante).
            if self.is_root_domain(host_hostname) or self.is_root_domain(header_hostname):
                connection.set_schema_to_public()
                self._set_request_public(request, settings.MAIN_DOMAIN)
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
                        "appelée avec l'en-tête X-Tenant-Domain (ou depuis son sous-domaine, "
                        "ex: moncampus.{}), pas depuis le domaine racine seul.".format(settings.MAIN_DOMAIN),
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

            # Ni tenant résolu, ni domaine racine : soit le hostname
            # n'appartient carrément pas à la plateforme (INVALID_DOMAIN),
            # soit il a la forme d'un sous-domaine de MAIN_DOMAIN /
            # d'un domaine enregistré mais sans Tenant correspondant en
            # base (TENANT_NOT_FOUND).
            if not self.is_valid_domain(hostname):
                return self._handle_error_response(
                    request,
                    "Domaine ou tenant introuvable.",
                    "INVALID_DOMAIN",
                    404
                )

            return self._handle_error_response(
                request,
                "Domaine ou tenant introuvable.",
                "TENANT_NOT_FOUND",
                404
            )

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