"""
moderation/models.py
=======================

`type_contenu` + `contenu_id` restent volontairement de simples champs
typés (pas de GenericForeignKey) : conformément à la convention du
Socle commun, `EntitePolymorphiqueMixin` est réservé aux deux entités
transverses (Journal d'Événement, File de Synchronisation) — voir
common/models.py.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class TypeContenuSignale(models.TextChoices):
    NEWS = 'news', _('News')
    COMMENTAIRE = 'commentaire', _('Commentaire')
    UTILISATEUR = 'utilisateur', _('Utilisateur')
    SONDAGE = 'sondage', _('Sondage')


class MotifSignalement(models.TextChoices):
    SPAM = 'spam', _('Spam')
    PROPOS_INAPPROPRIES = 'propos_inappropries', _('Propos inappropriés')
    DESINFORMATION = 'desinformation', _('Désinformation')
    HARCELEMENT = 'harcelement', _('Harcèlement')
    AUTRE = 'autre', _('Autre')


class SignalementStatutChoices(models.TextChoices):
    EN_ATTENTE = 'en_attente', _('En attente')
    TRAITE = 'traite', _('Traité')
    REJETE = 'rejete', _('Rejeté')


class Signalement(SocleTracabilite):
    statut = models.CharField(
        _('Statut'), max_length=20, choices=SignalementStatutChoices.choices,
        default=SignalementStatutChoices.EN_ATTENTE, db_index=True,
    )

    type_contenu = models.CharField(_('Type de contenu'), max_length=20, choices=TypeContenuSignale.choices)
    contenu_id = models.CharField(_('Identifiant du contenu'), max_length=50)
    titre_ou_apercu = models.CharField(_('Titre ou aperçu'), max_length=255)
    motif = models.CharField(_('Motif'), max_length=30, choices=MotifSignalement.choices)
    description = models.TextField(_('Description'), blank=True)
    auteur_signalement = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Auteur du signalement'),
        on_delete=models.CASCADE, related_name='signalements_emis',
    )

    class Meta:
        verbose_name = _('Signalement')
        verbose_name_plural = _('Signalements')
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['statut']), models.Index(fields=['type_contenu', 'contenu_id'])]

    def __str__(self):
        return f'{self.get_type_contenu_display()} — {self.titre_ou_apercu[:40]}'
