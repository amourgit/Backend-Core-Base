"""
Configuration des routes publiques et protégées
"""
# Versions d'API supportées
API_VERSIONS = ['v1', 'v2']

def generate_versioned_routes(base_routes_with_subpaths):
    """
    Génère les routes versionnées avec format /api/route/vX/subpath
    
    Args:
        base_routes_with_subpaths: Liste de tuples (route_base, subpaths)
        où subpaths peut être une liste de sous-chemins ou None pour juste la route de base
    
    Example:
        [('token', ['refresh', 'logout']), ('users', None)]
        génère: /api/token/v1/refresh, /api/token/v1/logout, /api/users/v1/
    """
    versioned_routes = []
    
    for route_config in base_routes_with_subpaths:
        if isinstance(route_config, tuple):
            base_route, subpaths = route_config
        else:
            # Si c'est juste une string, on assume pas de sous-chemins
            base_route, subpaths = route_config, None
        
        for version in API_VERSIONS:
            if subpaths:
                # Routes avec sous-chemins : /api/base_route/vX/subpath
                for subpath in subpaths:
                    route = f'/api/{base_route}/{version}/{subpath}'.rstrip('/')
                    versioned_routes.append(route)
            else:
                # Route de base seulement : /api/base_route/vX/
                route = f'/api/{base_route}/{version}'.rstrip('/')
                versioned_routes.append(route)
    
    return versioned_routes

def generate_non_versioned_routes(base_routes):
    """Génère les routes sans version avec préfixe /api/"""
    return [f'/api/{route}'.rstrip('/') for route in base_routes]




# Configuration des routes versionnées avec leurs sous-chemins
BASE_VERSIONED_GLOBAL_PUBLIC_ROUTES = [
    # ('token', ['refresh', 'sessions']),            # /api/token/vX/refresh
]
# Routes non versionnées (directement sous /api/)
BASE_NON_VERSIONED_GLOBAL_PUBLIC_ROUTES = [
    'health',                       # /api/health
    'swagger',                       # /api/swagger/vX/
    'redoc',
]

BASE_VERSIONED_TENANT_PUBLIC_ROUTES = [
    # Auparavant ('tenants', ['create']) générait /api/tenants/vX/create,
    # qui ne correspond à AUCUNE URL réelle : tenants/api/v1/urls.py monte
    # TenantCreateAPIView sur la racine ('') de son include, donc l'URL
    # réelle est /api/tenants/vX (sans suffixe). Corrigé.
    ('tenants', None),                 # /api/tenants/vX  (création d'un tenant)

    # CustomTokenObtainPairView (login) est lui aussi monté sur la racine
    # de token_manager/api/v1/urls.py -> /api/token/vX (pas de suffixe
    # 'obten' comme l'ancienne config le supposait, ce qui rendait le
    # login introuvable dans cette liste). Corrigé.
    ('token', None),                   # /api/token/vX          (login)
    ('token', ['refresh', 'check-token', 'register', 'google']),  # /api/token/vX/{refresh,check-token,register,google}

    # NB : 'refresh' et 'check-token' DOIVENT rester TENANT_PUBLIC, pas
    # seulement pour l'accès anonyme, mais parce que ces vues reçoivent
    # volontairement un access_token potentiellement EXPIRÉ (c'est tout
    # l'intérêt d'un refresh / d'une vérification de validité). Si elles
    # étaient classées ailleurs, le TenantJWTMiddleware validerait le
    # Bearer token AVANT la vue et rejetterait en 401 un token expiré —
    # cassant précisément le cas d'usage que ces routes existent pour gérer.
    #
    # 'register' et 'google' sont publiques par nature : leur rôle est
    # justement d'établir une session pour un visiteur qui n'en a AUCUNE
    # encore (inscription, ou première connexion via Google) — exiger un
    # Bearer token pour y accéder serait un non-sens fonctionnel complet.

    # --- Domaines métier CIVITAS NEWS à lecture publique --------------------
    # Ces 6 apps ont toutes le même contrat d'autorisation, déjà implémenté
    # au niveau des `permission_classes` DRF de chaque vue (SAFE_METHODS
    # -> True pour tout le monde, écriture -> IsAuthenticated / rôle précis) :
    # lecture publique (y compris anonyme), écriture réservée aux comptes
    # authentifiés (voir common/permissions.py : LectureLibreEcritureModerateur,
    # LectureLibreEcritureAuthentifie, et les permissions dédiées de chaque
    # app : NewsPermission, CommentairePermission, SondagePermission,
    # LienPublicationPermission).
    #
    # Avant cet ajout, AUCUNE de ces 6 apps n'était classée nulle part dans
    # ce fichier alors que leurs URLs sont bien montées dans config/urls.py
    # -> tenants.middleware.TenantMiddleware.get_route_type() retournait
    # None pour absolument toutes leurs routes -> 404 "Type de route non
    # géré" systématique, AVANT même d'atteindre Django/DRF (qui les
    # protège pourtant déjà correctement via permission_classes). 100% des
    # endpoints de ces 6 apps étaient donc inaccessibles, authentifié ou non.
    #
    # Pourquoi TENANT_PUBLIC et pas AUTHENTICATED : la classification ici
    # est PAR CHEMIN, pas par méthode HTTP. Un GET (lecture publique) et un
    # POST (écriture protégée) sur `/api/news/v1/news/` partagent EXACTEMENT
    # le même chemin -- impossible de les distinguer à ce niveau. Classer
    # 'news' en AUTHENTICATED bloquerait donc aussi les lectures anonymes en
    # 401 avant même que la vue ne s'exécute, ce qui casserait le contrat
    # "lecture publique" explicitement voulu et déjà codé côté vues.
    # TENANT_PUBLIC laisse TenantJWTMiddleware ne PAS exiger de token, et
    # laisse DRF faire sa propre authentification (JWTAuthentication est
    # dans DEFAULT_AUTHENTICATION_CLASSES, indépendante de ce middleware) :
    # un token Bearer valide est donc quand même reconnu par la vue pour les
    # écritures, exactement comme pour 'refresh'/'check-token' ci-dessus.
    ('referentiels', None),   # /api/referentiels/vX  (categories, organisations, etablissements)
    ('news', None),           # /api/news/vX          (news, {id}/reactions, {id}/partager)
    ('commentaires', None),   # /api/commentaires/vX  (commentaires, {id}/vote, {id}/reactions, {id}/pin)
    ('sondages', None),       # /api/sondages/vX      (sondages, {id}/vote)
    ('liens', None),          # /api/liens/vX         (liens, {id}/acceder — tracking clic/scan 100% public)
    ('statistiques', None),   # /api/statistiques/vX  (globales — AllowAny pur, aucune écriture)
]
# Routes non versionnées (directement sous /api/)
# Volontairement VIDE : l'ancienne entrée bare 'tenants' (-> /api/tenants)
# ne correspondait à aucune URL réelle (le montage réel est toujours
# versionné, /api/tenants/vX) et créait un préfixe dangereusement large :
# comme TENANT_PUBLIC est vérifié avant AUTHENTICATED/ADMIN, toute future
# sous-route ajoutée sous /api/tenants/... aurait été rendue publique par
# accident. Ne rien lister ici force une classification explicite pour
# toute nouvelle route.
BASE_NON_VERSIONED_TENANT_PUBLIC_ROUTES = []



# Configuration des routes Authentifiées versionnées avec leurs sous-chemins
BASE_VERSIONED_AUTHENTICATED_ROUTES = [
    'users',                          # /api/users/vX/
    'databases',                      # /api/databases/vX/
    'gestion',                        # /api/gestion/vX/
    'projets',                        # /api/projets/vX/
    'workflow',                       # /api/workflow/vX/
    'endpoint',                       # /api/endpoint/vX/
    'securite',                       # /api/securite/vX/
    'transformation',                 # /api/transformation/vX/
    'regle',                         # /api/regle/vX/
    'format',                        # /api/format/vX/
    'journalisation',                # /api/journalisation/vX/
    'operation',                     # /api/operation/vX/
    # 'sessions' était auparavant dans TENANT_PUBLIC : SessionManagementView
    # lit request.user.id sans aucun garde-fou (ni permission_classes, ni
    # authentication_classes propres) -> avec l'ancienne classification,
    # un appel sans token ne recevait ni 401 ni 403, il plantait en 500
    # (AttributeError sur None.id). 'settings' et 'tokens' (le routeur DRF
    # de token_manager/api/v1/urls.py) n'étaient classés NULLE PART, donc
    # /api/token/vX/settings et /api/token/vX/tokens tombaient
    # systématiquement sur le 404 "Type de route non géré" du middleware,
    # avant même d'atteindre Django/DRF (qui les protège pourtant déjà via
    # IsAuthenticated). Corrigé.
    ('token', ['logout', 'settings', 'tokens', 'sessions']),  # /api/token/vX/logout|settings|tokens|sessions

    # domain/api/v1/urls.py expose DomainViewSet (IsAuthenticated +
    # IsAccessTokenTenant) sur /api/domain/vX/domains, mais rien dans cette
    # config ne classait /api/domain/... -> 404 systématique là aussi.
    ('domain', ['domains']),          # /api/domain/vX/domains

    # --- Domaines métier CIVITAS NEWS 100% privés ---------------------------
    # Contrairement au groupe TENANT_PUBLIC ci-dessus, ces 3 apps n'ont
    # AUCUN chemin public : chaque vue exige request.user authentifié pour
    # TOUTES les méthodes, y compris GET (voir NotificationPermission,
    # EstModerateurOuAdmin). Pas de conflit lecture/écriture sur un même
    # chemin ici -> AUTHENTICATED est le classement correct, et fait aussi
    # office de garde-fou en profondeur (échec rapide au niveau du
    # middleware, avant même que la vue ne s'exécute), à l'identique du
    # traitement déjà appliqué à 'domain' juste au-dessus.
    'notifications',   # /api/notifications/vX  (notifications, {id}/read, read-all — propres à chaque utilisateur)
    'journal',         # /api/journal/vX        (evenements — journal d'audit, lecture seule, modérateurs/admins)
    'moderation',      # /api/moderation/vX     (signalements, {id}/traiter, utilisateurs — modérateurs/admins)
]
# Configuration des routes Authentifiées non versionnées avec leurs sous-chemins
BASE_NON_VERSIONED_AUTHENTICATED_ROUTES = [
    'profile',                      # /api/profile
    'settings',                     # /api/settings
]




# Configuration des routes Admin versionnées avec leurs sous-chemins
BASE_VERSIONED_ADMIN_ROUTES = [
    # 'tenants',                       # /api/tenants/vX/
    'admin',                         # /api/admin/vX/
]
# Configuration des routes Admin non versionnées avec leurs sous-chemins
BASE_NON_VERSIONED_ADMIN_ROUTES = [
    'system/status',               # /api/system/status
]




# Génération des routes complètes
VERSIONED_PUBLIC_ROUTES = generate_versioned_routes(BASE_VERSIONED_GLOBAL_PUBLIC_ROUTES)
NON_VERSIONED_PUBLIC_ROUTES = generate_non_versioned_routes(BASE_NON_VERSIONED_GLOBAL_PUBLIC_ROUTES) + ["/media"]
VERSIONED_TENANT_PUBLIC_ROUTES = generate_versioned_routes(BASE_VERSIONED_TENANT_PUBLIC_ROUTES)
NON_VERSIONED_TENANT_PUBLIC_ROUTES = generate_non_versioned_routes(BASE_NON_VERSIONED_TENANT_PUBLIC_ROUTES)
GLOBAL_PUBLIC_ROUTES = VERSIONED_PUBLIC_ROUTES + NON_VERSIONED_PUBLIC_ROUTES
TENANT_PUBLIC_ROUTES = VERSIONED_TENANT_PUBLIC_ROUTES + NON_VERSIONED_TENANT_PUBLIC_ROUTES

# Génération des routes Authentifiées
VERSIONED_AUTHENTICATED_ROUTES = generate_versioned_routes(BASE_VERSIONED_AUTHENTICATED_ROUTES)
NON_VERSIONED_AUTHENTICATED_ROUTES = generate_non_versioned_routes(BASE_NON_VERSIONED_AUTHENTICATED_ROUTES)
AUTHENTICATED_ROUTES = VERSIONED_AUTHENTICATED_ROUTES + NON_VERSIONED_AUTHENTICATED_ROUTES

# Génération des routes Admin
VERSIONED_ADMIN_ROUTES = generate_versioned_routes(BASE_VERSIONED_ADMIN_ROUTES)
NON_VERSIONED_ADMIN_ROUTES = generate_non_versioned_routes(BASE_NON_VERSIONED_ADMIN_ROUTES)
ADMIN_ROUTES = VERSIONED_ADMIN_ROUTES + NON_VERSIONED_ADMIN_ROUTES


print("NON_VERSIONED_PUBLIC_ROUTES:", NON_VERSIONED_PUBLIC_ROUTES)



# Affichage pour vérification (à supprimer en production)
if __name__ == "__main__":
    print("=== ROUTES PUBLIQUES ===")
    for route in GLOBAL_PUBLIC_ROUTES:
        print(f"  {route}")
    
    print("\n=== ROUTES AUTHENTIFIÉES ===")
    for route in AUTHENTICATED_ROUTES:
        print(f"  {route}")
    
    print("\n=== ROUTES ADMIN ===")
    for route in ADMIN_ROUTES:
        print(f"  {route}")