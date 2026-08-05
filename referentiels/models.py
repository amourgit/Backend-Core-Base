"""
referentiels/models.py
========================

Données de référence partagées par les autres apps métier (news,
commentaires, users...) : catégories éditoriales, organisations
publiantes, établissements. Isolées par schéma tenant comme le reste
de la plateforme (pas de FK explicite vers `tenants.Tenant` — voir
`users/models.py` pour la même convention).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class Categorie(SocleTracabilite):
    """Catégorie éditoriale d'une News (ex: Vie Académique, Sport, Culture)."""

    nom = models.CharField(_('Nom'), max_length=100, unique=True)
    couleur = models.CharField(
        _('Couleur'), max_length=20, default='#5B4DFF',
        help_text=_('Couleur hexadécimale utilisée pour les badges/étiquettes côté frontend.'),
    )
    icone = models.CharField(
        _('Icône'), max_length=50, default='Newspaper',
        help_text=_("Nom d'icône du set EGEN utilisé côté frontend."),
    )
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        verbose_name = _('Catégorie')
        verbose_name_plural = _('Catégories')
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Organisation(SocleTracabilite):
    """Entité publiante au sein du tenant (association étudiante, administration, club...)."""

    class TypeOrganisation(models.TextChoices):
        ASSOCIATION_ETUDIANTE = 'association_etudiante', _('Association étudiante')
        ADMINISTRATION = 'administration', _('Administration')
        CLUB = 'club', _('Club')
        DEPARTEMENT = 'departement', _('Département académique')
        AUTRE = 'autre', _('Autre')

    nom = models.CharField(_('Nom'), max_length=150)
    logo = models.ImageField(_('Logo'), upload_to='organisations/logos/', null=True, blank=True)
    type = models.CharField(_('Type'), max_length=30, choices=TypeOrganisation.choices, default=TypeOrganisation.AUTRE)
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        verbose_name = _('Organisation')
        verbose_name_plural = _('Organisations')
        ordering = ['nom']

    def __str__(self):
        return self.nom


class Etablissement(SocleTracabilite):
    """Établissement scolaire/universitaire rattaché au tenant."""

    nom = models.CharField(_('Nom'), max_length=200)
    province = models.CharField(_('Province'), max_length=100)

    class Meta:
        verbose_name = _('Établissement')
        verbose_name_plural = _('Établissements')
        ordering = ['nom']
        indexes = [models.Index(fields=['province'])]

    def __str__(self):
        return self.nom
