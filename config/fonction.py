from rest_framework import status

# Header alternatif au sous-domaine de l'URL pour porter l'identité du
# tenant (domaine complet, ex: "civitas.localhost") -- utile quand le
# frontend et le backend ne sont pas sur le même sous-domaine
# (ports différents en dev : Vite sur :3000, Django sur :8000 -- deux
# origines distinctes, donc le Host vu par Django n'est PAS forcément
# celui affiché dans la barre d'adresse du navigateur), ou plus
# généralement chaque fois qu'un proxy/CDN intermédiaire pourrait
# réécrire le Host avant qu'il n'atteigne Django.
TENANT_DOMAIN_HEADER = 'HTTP_X_TENANT_DOMAIN'


def resolve_request_hostname(request):
    """
    Point UNIQUE de résolution du hostname utilisé pour identifier le
    tenant -- utilisé à la fois par tenants/middleware.py
    (TenantMiddleware, qui positionne le schema PostgreSQL) et par
    domain/api/v1/services.py (DomainService.get_sous_domaine_by_request,
    utilisé par le login/l'inscription/Google, qui résolvent leur propre
    tenant indépendamment du middleware). Centralisé ici pour que les
    deux mécanismes ne puissent jamais diverger.

    Priorité :
      1. En-tête X-Tenant-Domain, si présent et non vide (ex:
         "civitas.localhost") -- le frontend le pose systématiquement
         (voir services/api/token/tenantHost.ts côté frontend) à partir
         de sa PROPRE URL courante (window.location.hostname), donc
         correct même quand frontend et backend sont sur des origines
         différentes (ports distincts en dev).
      2. Sinon, l'en-tête Host standard de la requête HTTP (comportement
         historique, correct quand frontend et backend partagent le
         même domaine -- typiquement en production derrière un même
         reverse proxy).

    Ce n'est pas un mécanisme moins sûr que le Host header : les deux
    passent par la MÊME validation en aval (recherche exacte dans
    Domain.objects, voir TenantMiddleware.is_valid_domain /
    _resolve_tenant_with_cache) -- une valeur non enregistrée comme
    domaine actif échoue exactement pareil, quelle que soit sa
    provenance.
    """
    header_value = request.META.get(TENANT_DOMAIN_HEADER, '').strip().lower()
    if header_value:
        return header_value
    return request.get_host().split(':')[0].lower()


formatReponse = {
    'type': str or None,
    'titre': str or None,
    'message': str or None,
    'niveau': str or 1,
    'status': int or None
}

def request_header_token(request):
    formatReponse['type'] = 'error'
    formatReponse['titre'] = 'Informations Manquantes'
    formatReponse['niveau'] = 100
    formatReponse['message'] = ""
    formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)
    data = None
    if request.headers.get('Authorization') and request.headers.get('Authorization').split(' ')[1] != None:
        data = request.headers.get('Authorization').split(' ')[1]
    return data, formatReponse


def minute_to_seconde(minute):
    return minute * 60



