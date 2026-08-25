from domain.models import Domain
from tenants.models import Tenant
from django.conf import settings
from config.fonction import resolve_request_hostname


class DomainService:
    @staticmethod
    def get_domain_by_name(name):
        return Domain.objects.get(name=name)
    
    @staticmethod
    def get_domain_by_id(id):
        return Domain.objects.get(id=id)
    
    @staticmethod
    def get_sous_domaine_by_request(request):
        # Résolution centralisée (en-tête X-Tenant-Domain en priorité,
        # sinon Host) -- voir config/fonction.py:resolve_request_hostname.
        hostname = resolve_request_hostname(request)
        if not hostname:
            return None
        main_domain = getattr(settings, 'MAIN_DOMAIN', None)
        if main_domain and hostname.endswith('.' + main_domain):
            return hostname.split('.')[0]
        # Le hostname n'est PAS un sous-domaine de MAIN_DOMAIN : cas d'un
        # domaine de tenant enregistré ailleurs (ex: frontend Vercel,
        # backend Render -- voir tenants/middleware.py:TenantMiddleware.
        # is_valid_domain, cas 3, et bootstrap_tenant --extra-domain).
        # 1. Repli sur une recherche directe en base par domaine complet,
        # plutôt que de renvoyer None et casser tout appelant qui ne
        # passe QUE par un sous-domaine de MAIN_DOMAIN.
        domain_row = Domain.objects.filter(domain=hostname).select_related('tenant').first()
        if domain_row:
            return domain_row.tenant.sous_domaine

        # 2. Repli final : le hostname EST DIRECTEMENT le sous-domaine du
        # tenant (ex: en-tête X-Tenant-Domain positionné à la valeur nue
        # "civitasnews" via VITE_TENANT_HOST, sans qu'aucune ligne Domain
        # "civitasnews" ne soit enregistrée -- Domain.clean() exige de
        # toute façon un domaine avec au moins un point, donc une valeur
        # nue ne peut structurellement JAMAIS matcher le cas 1 ci-dessus).
        # Symétrique avec TenantMiddleware._resolve_tenant (voir
        # tenants/middleware.py), qui tente exactement ce même repli sur
        # Tenant.sous_domaine après l'échec de la recherche par domaine
        # complet. Avant ce correctif, cette fonction était STRICTEMENT
        # moins capable que celle du middleware : un en-tête que le
        # middleware résolvait avec succès (donc request.tenant déjà
        # positionné) pouvait quand même faire échouer cette fonction --
        # utilisée, elle, indépendamment du middleware par les vues de
        # login/inscription/Google/refresh (voir token_manager/api/v1/
        # views.py) -- avec un 400 "tenant introuvable" en production
        # (Render+Vercel, où seul l'en-tête, jamais un sous-domaine du
        # Host, porte l'identité du tenant), alors même que la requête
        # était en tout point valide.
        sous_domaine = hostname.split('.')[0]
        if Tenant.objects.filter(sous_domaine=sous_domaine).exists():
            return sous_domaine

        return None
    
    @staticmethod
    def update_all_domain_by_perform(data_get, data_update):
        return Domain.objects.filter(**data_get).all().update(**data_update)
    
