"""
notifications/models.py
==========================
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class NotificationFormat(models.TextChoices):
    ACTUALITE = 'actualite', _('Actualité')
    SONDAGE = 'sondage', _('Sondage')
    ANNONCE = 'annonce', _('Annonce')
    ALERTE = 'alerte', _('Alerte')
    CONSULTATION = 'consultation', _('Consultation')
    DECISION = 'decision', _('Décision')
    REFORME = 'reforme', _('Réforme')
    RAPPORT = 'rapport', _('Rapport')


class CategoryTab(models.TextChoices):
    ALL = 'all', _('Toutes')
    DIRECT = 'direct', _('Direct')
    NEWS = 'news', _('News')
    SONDAGES = 'sondages', _('Sondages')
    ALERTES = 'alertes', _('Alertes')


class Notification(SocleTracabilite):
    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Destinataire'),
        on_delete=models.CASCADE, related_name='notifications',
    )
    format = models.CharField(_('Format'), max_length=20, choices=NotificationFormat.choices)
    titre = models.CharField(_('Titre'), max_length=255)
    description = models.TextField(_('Description'), blank=True)

    categorie_nom = models.CharField(_('Catégorie — nom'), max_length=100)
    categorie_couleur = models.CharField(_('Catégorie — couleur'), max_length=20, default='#5B4DFF')
    categorie_icone = models.CharField(_('Catégorie — icône'), max_length=50, blank=True)

    lien = models.CharField(_('Lien'), max_length=500, blank=True)
    lu = models.BooleanField(_('Lu'), default=False, db_index=True)
    tag = models.CharField(_('Tag'), max_length=50, blank=True)
    urgente = models.BooleanField(_('Urgente'), default=False)
    category_tab = models.CharField(_('Onglet'), max_length=20, choices=CategoryTab.choices, default=CategoryTab.ALL)
    notice = models.TextField(_('Note'), blank=True)
    actions = models.JSONField(_('Actions'), default=list, blank=True)

    class Meta:
        verbose_name = _('Notification')
        verbose_name_plural = _('Notifications')
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['destinataire', 'lu'])]

    def __str__(self):
        return f'{self.destinataire} — {self.titre}'
