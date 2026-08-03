from django.db import models
from django_tenants.models import DomainMixin
from django.utils.translation import gettext_lazy as _
import re
from django.core.exceptions import ValidationError


# Create your models here.

class Domain(DomainMixin):
    """
    Modèle pour gérer les domaines des tenants.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='domains')
    domain = models.CharField(_('Domaine'), max_length=253, unique=True)
    is_primary = models.BooleanField(_('Domaine principal'), default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'is_primary'],
                condition=models.Q(is_primary=True),
                name='unique_primary_domain_per_tenant'
            )
        ]
        verbose_name = _('Domaine')
        verbose_name_plural = _('Domaines')
        ordering = ['domain']

    def __str__(self):
        return self.domain.lower()
    
    def clean(self):
       super().clean()
       if self.domain:
           # Vérifier le format du domaine
           if not re.match(r'^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$', self.domain):
               raise ValidationError(_('Format de domaine invalide'))

    def is_valid_domain(self):
       try:
           from django.core.validators import URLValidator
           validator = URLValidator()
           validator(f'http://{self.domain}')
           return True
       except:
           return False
       
    @classmethod
    def get_primary_domain(cls, tenant):
        return cls.objects.filter(tenant=tenant, is_primary=True).first()
    
    def get_domain_with_scheme(self):
        return f'http://{self.domain}'
    
    def get_domain_without_scheme(self):
        return self.domain


