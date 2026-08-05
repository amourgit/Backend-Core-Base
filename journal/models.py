"""
journal/models.py
====================

Implémente "E2.1 Journal d'Événement", l'une des DEUX SEULES entités
prévues par l'architecture pour utiliser `EntitePolymorphiqueMixin`
(voir common/models.py) — référencer, de façon polymorphe, n'importe
quelle entité de n'importe quelle app métier lors d'une action
d'administration/modération.

Correspond à `AuditLog` côté frontend (src/types/models/admin.types.ts).
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite, EntitePolymorphiqueMixin


class TypeActionJournal(models.TextChoices):
    CREATION = 'creation', _('Création')
    MODIFICATION = 'modification', _('Modification')
    SUPPRESSION = 'suppression', _('Suppression')
    PUBLICATION = 'publication', _('Publication')
    MODERATION = 'moderation', _('Modération')
    CONNEXION = 'connexion', _('Connexion')
    AUTRE = 'autre', _('Autre')


class EvenementJournal(SocleTracabilite, EntitePolymorphiqueMixin):
    """Une ligne = un événement d'administration/modération journalisé.
    Volontairement en lecture seule côté API (jamais modifiable a
    posteriori — l'intégrité du journal est la seule raison d'être)."""

    action = models.CharField(_('Action'), max_length=30, choices=TypeActionJournal.choices)
    # Snapshot texte de la cible, pour que le journal reste lisible même
    # si l'entité référencée (entite_reference) est plus tard supprimée.
    cible_libelle = models.CharField(_('Cible (libellé)'), max_length=255, blank=True)
    details = models.JSONField(_('Détails'), default=dict, blank=True)
    adresse_ip = models.GenericIPAddressField(_('Adresse IP'), null=True, blank=True)

    class Meta:
        verbose_name = _("Événement de journal")
        verbose_name_plural = _('Événements de journal')
        ordering = ['-cree_le']
        indexes = [models.Index(fields=['action']), models.Index(fields=['entite_type', 'entite_id'])]

    def __str__(self):
        return f'{self.get_action_display()} — {self.cible_libelle}'

    @classmethod
    def consigner(cls, action, utilisateur=None, cible=None, cible_libelle='', details=None, adresse_ip=None, systeme=''):
        """Point d'entrée unique pour journaliser un événement depuis
        n'importe quelle app (moderation, news, users...)."""
        entite_type = None
        entite_id = None
        if cible is not None:
            from django.contrib.contenttypes.models import ContentType
            entite_type = ContentType.objects.get_for_model(cible)
            entite_id = cible.pk
            if not cible_libelle:
                cible_libelle = str(cible)

        return cls.objects.create(
            action=action,
            cree_par=utilisateur,
            cree_par_systeme=systeme,
            entite_type=entite_type,
            entite_id=entite_id,
            cible_libelle=cible_libelle,
            details=details or {},
            adresse_ip=adresse_ip,
        )
