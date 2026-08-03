from domain.models import Domain
from django.conf import settings


class DomainService:
    @staticmethod
    def get_domain_by_name(name):
        return Domain.objects.get(name=name)
    
    @staticmethod
    def get_domain_by_id(id):
        return Domain.objects.get(id=id)
    
    @staticmethod
    def get_sous_domaine_by_request(request):
        # Recherche du sous-domaine dans l'url
        hostname = request.get_host().split(':')[0].lower()
        main_domain = getattr(settings, 'MAIN_DOMAIN', None)
        sous_domaine = None
        if main_domain and hostname.endswith('.' + main_domain):
            sous_domaine = hostname.split('.')[0]
            print(sous_domaine)
        return sous_domaine
    
    @staticmethod
    def update_all_domain_by_perform(data_get, data_update):
        return Domain.objects.filter(**data_get).all().update(**data_update)
    
