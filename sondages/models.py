"""
sondages/models.py
=====================
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class TypeVoteSondage(models.TextChoices):
    UNIQUE = 'unique', _('Choix unique')
    MULTIPLE = 'multiple', _('Choix multiple')


class VisibiliteResultatSondage(models.TextChoices):
    INSTANTANE = 'instantane', _('Instantané')
    MASQUE_JUSQUA_FIN = 'masque_jusqua_fin', _("Masqué jusqu'à la fin")


class SondageStatutChoices(models.TextChoices):
    ACTIF = 'actif', _('Actif')
    PROGRAMME = 'programme', _('Programmé')
    TERMINE = 'termine', _('Terminé')
    ARCHIVE = 'archive', _('Archivé')


class Sondage(SocleTracabilite):
    statut = models.CharField(
        _('Statut'), max_length=20, choices=SondageStatutChoices.choices, default=SondageStatutChoices.ACTIF,
        db_index=True,
    )

    news = models.ForeignKey(
        'news.News', verbose_name=_('News'), on_delete=models.CASCADE, related_name='sondages',
    )
    titre = models.CharField(_('Titre'), max_length=255)
    description = models.TextField(_('Description'), blank=True)
    question = models.CharField(_('Question'), max_length=500)
    image = models.ImageField(_('Image'), upload_to='sondages/', null=True, blank=True)

    date_debut = models.DateTimeField(_('Date de début'))
    date_fin = models.DateTimeField(_('Date de fin'))

    type_vote = models.CharField(_('Type de vote'), max_length=10, choices=TypeVoteSondage.choices, default=TypeVoteSondage.UNIQUE)
    anonymat = models.BooleanField(_('Anonymat'), default=True)
    visibilite_resultat = models.CharField(
        _('Visibilité du résultat'), max_length=25,
        choices=VisibiliteResultatSondage.choices, default=VisibiliteResultatSondage.INSTANTANE,
    )

    class Meta:
        verbose_name = _('Sondage')
        verbose_name_plural = _('Sondages')
        ordering = ['-cree_le']

    def __str__(self):
        return self.titre


class ChoixSondage(models.Model):
    sondage = models.ForeignKey(Sondage, verbose_name=_('Sondage'), on_delete=models.CASCADE, related_name='choix')
    libelle = models.CharField(_('Libellé'), max_length=255)
    image = models.ImageField(_('Image'), upload_to='sondages/choix/', null=True, blank=True)
    ordre = models.PositiveSmallIntegerField(_('Ordre'), default=0)

    class Meta:
        verbose_name = _('Choix de sondage')
        verbose_name_plural = _('Choix de sondage')
        ordering = ['ordre']

    def __str__(self):
        return self.libelle


class VoteSondage(models.Model):
    sondage = models.ForeignKey(Sondage, verbose_name=_('Sondage'), on_delete=models.CASCADE, related_name='votes')
    choix = models.ForeignKey(ChoixSondage, verbose_name=_('Choix'), on_delete=models.CASCADE, related_name='votes')
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Utilisateur'),
        on_delete=models.CASCADE, related_name='votes_sondages',
    )
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Vote (sondage)')
        verbose_name_plural = _('Votes (sondages)')
        constraints = [
            models.UniqueConstraint(fields=['choix', 'utilisateur'], name='vote_sondage_unique_par_choix_utilisateur')
        ]
