"""
news/models.py
================

Domaine News (alias historique côté frontend : "Sujet"). Toutes les
données agrégées (vues, réactions par type, votes, commentaires) sont
CALCULÉES à la volée à partir des tables de faits ci-dessous plutôt que
stockées de façon dénormalisée — le backend fournit des chiffres
toujours exacts, le frontend n'a aucun calcul à faire.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite, StatutCycleVie


class NewsType(models.TextChoices):
    PROJET = 'projet', _('Projet')
    EVENEMENT = 'evenement', _('Événement')
    ANNONCE = 'annonce', _('Annonce')
    SONDAGE = 'sondage', _('Sondage')
    CONSULTATION = 'consultation', _('Consultation')
    PETITION = 'petition', _('Pétition')
    INFORMATION = 'information', _('Information')
    REFORME = 'reforme', _('Réforme')
    IDEE = 'idee', _('Idée')
    CONFERENCE = 'conference', _('Conférence')
    REUNION = 'reunion', _('Réunion')
    ATELIER = 'atelier', _('Atelier')
    APPEL_PARTICIPATION = 'appel_participation', _('Appel à participation')
    ARTICLE = 'article', _('Article')
    PUBLICATION = 'publication', _('Publication')
    ACTUALITE = 'actualite', _('Actualité')


class NewsStatutChoices(models.TextChoices):
    """Cycle de vie spécifique à News — restreint le `StatutCycleVie`
    générique du Socle de Traçabilité (voir common/models.py)."""
    BROUILLON = 'brouillon', _('Brouillon')
    PUBLIE = 'publie', _('Publié')
    ARCHIVE = 'archive', _('Archivé')
    SIGNALE = 'signale', _('Signalé')


class Visibilite(models.TextChoices):
    PUBLIC = 'public', _('Public')
    PRIVE = 'prive', _('Privé')
    LIMITE = 'limite', _('Limité')


class TypeReaction(models.TextChoices):
    COEUR = 'coeur', _('Cœur')
    JAIME = 'jaime', _("J'aime")
    BRAVO = 'bravo', _('Bravo')
    YOUPI = 'youpi', _('Youpi')
    WOW = 'wow', _('Wow')
    JAIMEPAS = 'jaimepas', _("Je n'aime pas")


class Province(models.TextChoices):
    """Les 9 provinces du Gabon — liste fixe, ne justifie pas une table
    de référence dédiée."""
    ESTUAIRE = 'Estuaire', _('Estuaire')
    HAUT_OGOOUE = 'Haut-Ogooué', _('Haut-Ogooué')
    MOYEN_OGOOUE = 'Moyen-Ogooué', _('Moyen-Ogooué')
    NGOUNIE = 'Ngounié', _('Ngounié')
    NYANGA = 'Nyanga', _('Nyanga')
    OGOOUE_IVINDO = 'Ogooué-Ivindo', _('Ogooué-Ivindo')
    OGOOUE_LOLO = 'Ogooué-Lolo', _('Ogooué-Lolo')
    OGOOUE_MARITIME = 'Ogooué-Maritime', _('Ogooué-Maritime')
    WOLEU_NTEM = 'Woleu-Ntem', _('Woleu-Ntem')


class Tag(models.Model):
    """Étiquette libre réutilisable, pour le filtrage/la recherche (référentiel simple)."""
    nom = models.CharField(_('Nom'), max_length=50, unique=True)

    class Meta:
        verbose_name = _('Étiquette')
        verbose_name_plural = _('Étiquettes')
        ordering = ['nom']

    def __str__(self):
        return self.nom


class News(SocleTracabilite):
    """Entité centrale : une actualité/publication de la plateforme."""

    statut = models.CharField(
        _('Statut'), max_length=30, choices=NewsStatutChoices.choices, default=NewsStatutChoices.BROUILLON,
        db_index=True,
    )

    slug = models.SlugField(_('Slug'), max_length=255, unique=True, db_index=True)
    type = models.CharField(_('Type'), max_length=30, choices=NewsType.choices, default=NewsType.INFORMATION)
    titre = models.CharField(_('Titre'), max_length=255)
    description = models.TextField(_('Description'))
    contenu = models.TextField(_('Contenu'), blank=True)
    image = models.ImageField(_('Image de couverture'), upload_to='news/couvertures/', null=True, blank=True)

    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Auteur'),
        on_delete=models.PROTECT, related_name='news_publiees',
    )
    organisation = models.ForeignKey(
        'referentiels.Organisation', verbose_name=_('Organisation'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='news',
    )
    etablissement = models.ForeignKey(
        'referentiels.Etablissement', verbose_name=_('Établissement'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='news',
    )
    categorie = models.ForeignKey(
        'referentiels.Categorie', verbose_name=_('Catégorie'),
        on_delete=models.PROTECT, related_name='news',
    )
    tags = models.ManyToManyField(Tag, verbose_name=_('Étiquettes'), blank=True, related_name='news')

    province = models.CharField(_('Province'), max_length=30, choices=Province.choices, blank=True)
    lieu = models.CharField(_('Lieu'), max_length=255, blank=True)
    date_debut = models.DateTimeField(_('Date de début'), null=True, blank=True)
    date_fin = models.DateTimeField(_('Date de fin'), null=True, blank=True)

    visibilite = models.CharField(_('Visibilité'), max_length=20, choices=Visibilite.choices, default=Visibilite.PUBLIC)

    # Compteur simple (pas de valeur analytique par lui-même contrairement
    # aux vues, donc pas besoin d'une table de faits dédiée).
    partages = models.PositiveIntegerField(_('Partages'), default=0)

    class Meta:
        verbose_name = _('News')
        verbose_name_plural = _('News')
        ordering = ['-cree_le']
        indexes = [
            models.Index(fields=['statut', 'visibilite']),
            models.Index(fields=['type']),
            models.Index(fields=['province']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.titre


class NewsVue(models.Model):
    """Table de faits : une ligne par consultation d'une News. Permet un
    comptage de vues exact ET des statistiques temporelles réelles
    (activité par heure/jour) sans dénormaliser un compteur sur `News`."""
    news = models.ForeignKey(News, verbose_name=_('News'), on_delete=models.CASCADE, related_name='vues')
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Utilisateur'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    horodatage = models.DateTimeField(_('Horodatage'), auto_now_add=True, db_index=True)
    adresse_ip = models.GenericIPAddressField(_('Adresse IP'), null=True, blank=True)

    class Meta:
        verbose_name = _('Vue de News')
        verbose_name_plural = _('Vues de News')
        indexes = [models.Index(fields=['news', 'horodatage'])]


class ReactionNews(models.Model):
    """Une réaction (au sens 'réseau social') sur une News.
    Réactions illimitées par utilisateur et anonymes autorisées."""
    news = models.ForeignKey(News, verbose_name=_('News'), on_delete=models.CASCADE, related_name='reactions')
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_('Utilisateur'),
        null=True, blank=True, on_delete=models.CASCADE, related_name='reactions_news',
    )
    type_reaction = models.CharField(_('Type de réaction'), max_length=20, choices=TypeReaction.choices)
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Réaction (News)')
        verbose_name_plural = _('Réactions (News)')
        # Plus de contrainte d'unicité - réactions illimitées autorisées


class NewsMedia(models.Model):
    """Média riche attaché à une News (vidéo, audio, document intégré, image annotée)."""

    class TypeMedia(models.TextChoices):
        IMAGE = 'image', _('Image')
        VIDEO = 'video', _('Vidéo')
        YOUTUBE = 'youtube', _('YouTube')
        AUDIO = 'audio', _('Audio')
        DOCUMENT = 'document', _('Document')

    news = models.ForeignKey(News, verbose_name=_('News'), on_delete=models.CASCADE, related_name='medias')
    type = models.CharField(_('Type'), max_length=20, choices=TypeMedia.choices)
    fichier = models.FileField(_('Fichier'), upload_to='news/medias/', null=True, blank=True)
    url_externe = models.URLField(_('URL externe'), blank=True, help_text=_('Pour les médias hébergés ailleurs (ex: YouTube).'))
    vignette = models.ImageField(_('Vignette'), upload_to='news/medias/vignettes/', null=True, blank=True)
    titre = models.CharField(_('Titre'), max_length=255)
    description = models.TextField(_('Description'), blank=True)
    duree = models.CharField(_('Durée'), max_length=20, blank=True, help_text=_("Format libre, ex: '3:45'."))
    ordre = models.PositiveSmallIntegerField(_('Ordre'), default=0)
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Média (News)')
        verbose_name_plural = _('Médias (News)')
        ordering = ['ordre', 'cree_le']

    def __str__(self):
        return self.titre or f'Média #{self.pk}'


class NewsImageGalerie(models.Model):
    """Image simple de galerie (distincte de NewsMedia, plus riche/typé)."""
    news = models.ForeignKey(News, verbose_name=_('News'), on_delete=models.CASCADE, related_name='galerie')
    image = models.ImageField(_('Image'), upload_to='news/galerie/')
    legende = models.CharField(_('Légende'), max_length=255, blank=True)
    ordre = models.PositiveSmallIntegerField(_('Ordre'), default=0)

    class Meta:
        verbose_name = _('Image de galerie')
        verbose_name_plural = _('Images de galerie')
        ordering = ['ordre']


class DocumentJoint(models.Model):
    """Document téléchargeable attaché à une News (PDF, etc.)."""
    news = models.ForeignKey(News, verbose_name=_('News'), on_delete=models.CASCADE, related_name='documents')
    nom = models.CharField(_('Nom'), max_length=255)
    fichier = models.FileField(_('Fichier'), upload_to='news/documents/')
    taille = models.PositiveIntegerField(_('Taille (octets)'), default=0, editable=False)
    type = models.CharField(_('Type MIME'), max_length=100, blank=True)
    cree_le = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Document joint')
        verbose_name_plural = _('Documents joints')
        ordering = ['-cree_le']

    def save(self, *args, **kwargs):
        if self.fichier and not self.taille:
            try:
                self.taille = self.fichier.size
            except (OSError, ValueError):
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nom
