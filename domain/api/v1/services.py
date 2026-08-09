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
        sous_domaine = None
        if main_domain and hostname.endswith('.' + main_domain):
            sous_domaine = hostname.split('.')[0]
        return sous_domaine
    
    @staticmethod
    def update_all_domain_by_perform(data_get, data_update):
        return Domain.objects.filter(**data_get).all().update(**data_update)
    
