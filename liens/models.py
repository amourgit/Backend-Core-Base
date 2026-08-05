"""
liens/models.py
==================

Le comptage clics/scans est calculé depuis `LienAcces` (table de faits),
jamais stocké en compteur dénormalisé — cohérent avec le reste de la
plateforme (voir news/models.py:NewsVue pour le même principe).
"""

import secrets
import string

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


def _generer_code_court(longueur=7):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(longueur))


class Visibilite(models.TextChoices):
    PUBLIC = 'public', _('Public')
    PRIVE = 'prive', _('Privé')
    LIMITE = 'limite', _('Limité')


class LienPublication(SocleTracabilite):
    news = models.ForeignKey(
        'news.News', verbose_name=_('News'), on_delete=models.CASCADE, related_name='liens_publication',
    )
    url_publique = models.URLField(_('URL publique'), max_length=500)
    code_court = models.CharField(_('Code court'), max_length=20, unique=True, default=_generer_code_court)
    qr_code = models.ImageField(_('QR code'), upload_to='liens/qrcodes/', null=True, blank=True)

    visibilite = models.CharField(_('Visibilité'), max_length=20, choices=Visibilite.choices, default=Visibilite.PUBLIC)
    mot_de_passe_hash = models.CharField(_('Mot de passe (haché)'), max_length=255, blank=True)
    expiration = models.DateTimeField(_('Expiration'), null=True, blank=True)
    usage_unique = models.BooleanField(_('Usage unique'), default=False)
    deja_utilise = models.BooleanField(_('Déjà utilisé'), default=False, editable=False)

    # Portée de diffusion ciblée (texte libre descriptif, pas une FK :
    # décrit une audience, pas une entité à part entière).
    scope_etablissement = models.CharField(_('Établissement (portée)'), max_length=200, blank=True)
    scope_province = models.CharField(_('Province (portée)'), max_length=100, blank=True)
    scope_promotion = models.CharField(_('Promotion (portée)'), max_length=100, blank=True)
    scope_organisation = models.CharField(_('Organisation (portée)'), max_length=200, blank=True)
    scope_classe = models.CharField(_('Classe (portée)'), max_length=100, blank=True)

    class Meta:
        verbose_name = _('Lien de publication')
        verbose_name_plural = _('Liens de publication')
        ordering = ['-cree_le']

    @property
    def a_mot_de_passe(self):
        return bool(self.mot_de_passe_hash)

    def __str__(self):
        return f'{self.news.titre} — {self.code_court}'


class LienAcces(models.Model):
    """Table de faits : un accès (clic ou scan QR) à un lien de publication."""

    class TypeAcces(models.TextChoices):
        CLIC = 'clic', _('Clic')
        SCAN = 'scan', _('Scan QR')

    lien = models.ForeignKey(LienPublication, verbose_name=_('Lien'), on_delete=models.CASCADE, related_name='acces')
    type_acces = models.CharField(_("Type d'accès"), max_length=10, choices=TypeAcces.choices)
    horodatage = models.DateTimeField(_('Horodatage'), auto_now_add=True, db_index=True)
    adresse_ip = models.GenericIPAddressField(_('Adresse IP'), null=True, blank=True)

    class Meta:
        verbose_name = _("Accès à un lien")
        verbose_name_plural = _('Accès aux liens')
        indexes = [models.Index(fields=['lien', 'type_acces'])]
