from domain.models import Domain
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
        main_domain = getattr(settings, 'MAIN_DOMAIN', None)
        if main_domain and hostname.endswith('.' + main_domain):
            return hostname.split('.')[0]
        # Le hostname n'est PAS un sous-domaine de MAIN_DOMAIN : cas d'un
        # domaine de tenant enregistré ailleurs (ex: frontend Vercel,
        # backend Render -- voir tenants/middleware.py:TenantMiddleware.
        # is_valid_domain, cas 3, et bootstrap_tenant --extra-domain).
        # Repli sur une recherche directe en base par domaine complet,
        # plutôt que de renvoyer None et casser tout appelant qui ne
        # passe QUE par un sous-domaine de MAIN_DOMAIN.
        domain_row = Domain.objects.filter(domain=hostname).select_related('tenant').first()
        return domain_row.tenant.sous_domaine if domain_row else None
    
    @staticmethod
    def update_all_domain_by_perform(data_get, data_update):
        return Domain.objects.filter(**data_get).all().update(**data_update)
    
