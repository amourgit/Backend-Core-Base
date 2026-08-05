"""
commentaires/models.py
=========================

Fil de discussion sous une News. `estAdministrateur` (badge affiché
côté frontend) n'est JAMAIS stocké : calculé à la volée depuis le rôle
courant de l'auteur, pour ne jamais afficher une information périmée
si le rôle change après coup.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class TypeContenuCommentaire(models.TextChoices):
    TEXTE = 'texte', _('Texte')
    AUDIO = 'audio', _('Audio')


class Commentaire(SocleTracabilite):
    news = models.ForeignKey(
        'news.News', verbose_name=_('News'), on_delete=models.CASCADE, related_name='commentaires',
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Auteur'),
        on_delete=models.PROTECT, related_name='commentaires_publies',
    )
    type_contenu = models.CharField(
        _('Type de contenu'), max_length=10, choices=TypeContenuCommentaire.choices, default=TypeContenuCommentaire.TEXTE,
    )
    contenu = models.TextField(_('Contenu'), blank=True)
    audio_fichier = models.FileField(_('Fichier audio'), upload_to='commentaires/audio/', null=True, blank=True)
    audio_duration = models.PositiveIntegerField(_('Durée audio (secondes)'), null=True, blank=True)

    reponse_a = models.ForeignKey(
        'self', verbose_name=_('En réponse à'), null=True, blank=True,
        on_delete=models.CASCADE, related_name='reponses',
    )
    mentions = models.ManyToManyField(
        settings.AUTH_USER_MODEL, verbose_name=_('Mentions'), blank=True, related_name='commentaires_mentionne',
    )

    est_epingle = models.BooleanField(_('Épinglé'), default=False)
    est_reponse_acceptee = models.BooleanField(_('Réponse acceptée'), default=False)

    class Meta:
        verbose_name = _('Commentaire')
        verbose_name_plural = _('Commentaires')
        ordering = ['-cree_le']
        indexes = [
            models.Index(fields=['news', 'est_epingle']),
            models.Index(fields=['reponse_a']),
        ]

    def __str__(self):
        return f'{self.auteur} — {self.contenu[:50]}'


class MediaJointCommentaire(models.Model):
    class TypeMedia(models.TextChoices):
        IMAGE = 'image', _('Image')
        GIF = 'gif', _('GIF')
        AUDIO = 'audio', _('Audio')
        VIDEO = 'video', _('Vidéo')
        DOCUMENT = 'document', _('Document')

    commentaire = models.ForeignKey(Commentaire, verbose_name=_('Commentaire'), on_delete=models.CASCADE, related_name='medias')
    type = models.CharField(_('Type'), max_length=20, choices=TypeMedia.choices)
    fichier = models.FileField(_('Fichier'), upload_to='commentaires/medias/', null=True, blank=True)
    url_externe = models.URLField(_('URL externe'), blank=True)

    class Meta:
        verbose_name = _('Média joint (commentaire)')
        verbose_name_plural = _('Médias joints (commentaires)')


class ReactionCommentaire(models.Model):
    """Réaction libre (emoji ou libellé court) — non restreinte à un
    catalogue fixe contrairement aux réactions de News, pour rester
    flexible côté frontend."""
    commentaire = models.ForeignKey(Commentaire, verbose_name=_('Commentaire'), on_delete=models.CASCADE, related_name='reactions')
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Utilisateur'),
        on_delete=models.CASCADE, related_name='reactions_commentaires',
    )
    type_reaction = models.CharField(_('Type de réaction'), max_length=30)
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Réaction (commentaire)')
        verbose_name_plural = _('Réactions (commentaires)')
        constraints = [
            models.UniqueConstraint(
                fields=['commentaire', 'utilisateur', 'type_reaction'], name='reaction_commentaire_unique',
            )
        ]


class VoteCommentaire(models.Model):
    class Direction(models.TextChoices):
        UP = 'up', _('Positif')
        DOWN = 'down', _('Négatif')

    commentaire = models.ForeignKey(Commentaire, verbose_name=_('Commentaire'), on_delete=models.CASCADE, related_name='votes')
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Utilisateur'),
        on_delete=models.CASCADE, related_name='votes_commentaires',
    )
    direction = models.CharField(_('Direction'), max_length=10, choices=Direction.choices)
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Vote (commentaire)')
        verbose_name_plural = _('Votes (commentaires)')
        constraints = [
            models.UniqueConstraint(fields=['commentaire', 'utilisateur'], name='vote_commentaire_unique_par_utilisateur')
        ]
