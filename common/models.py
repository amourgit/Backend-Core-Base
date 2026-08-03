"""
Socle Commun — EGEN / EDUNET GABON
===================================

Ce module porte les briques transversales réutilisées par TOUTES les entités
métier de la plateforme, quel que soit leur système (A1..A3, B1..B4, E1..E3).

Aucun modèle concret n'est défini ici : uniquement des classes abstraites,
des choix (TextChoices) et des managers, destinés à être hérités.

Voir la cartographie des entités (Niveau 0 à Transverse) : chaque entité,
sans exception, hérite de `SocleTracabilite`. Les entités à caractère
temporel héritent en plus de `PeriodeValiditeMixin`.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Choix communs
# ---------------------------------------------------------------------------

class OrigineDonnee(models.TextChoices):
    """Origine de la donnée — champ obligatoire du Socle de Traçabilité."""
    SAISIE_MANUELLE = 'saisie_manuelle', _('Saisie manuelle')
    IMPORTEE = 'importee', _('Importée')
    SYNCHRONISEE = 'synchronisee', _('Synchronisée depuis un autre système')
    GENEREE_AUTO = 'generee_auto', _('Générée automatiquement')


class StatutCycleVie(models.TextChoices):
    """
    Statut générique du cycle de vie d'une entité.
    Chaque entité peut restreindre/étendre ces valeurs via son propre
    `STATUT_CHOICES` si son cycle de vie métier diffère (ex: Cellule,
    Affectation, Souscription...). Ce jeu de valeurs sert de valeur par
    défaut raisonnable et documente l'intention : jamais de suppression
    physique, toujours un statut.
    """
    ACTIF = 'actif', _('Actif')
    SUSPENDU = 'suspendu', _('Suspendu')
    ARCHIVE = 'archive', _('Archivé')
    CLOTURE = 'cloture', _('Clôturé')


# ---------------------------------------------------------------------------
# Manager — exclut par défaut les entités supprimées logiquement
# ---------------------------------------------------------------------------

class EntiteQuerySet(models.QuerySet):
    def actifs(self):
        return self.filter(supprime_le__isnull=True)

    def supprimes(self):
        return self.exclude(supprime_le__isnull=True)


class EntiteManager(models.Manager):
    """Manager par défaut : retourne tout (y compris les supprimés logiques),
    pour ne jamais masquer silencieusement des données à l'administration
    ou à l'audit. Utiliser `.actifs()` explicitement côté métier/API pour
    filtrer les enregistrements supprimés logiquement."""

    def get_queryset(self):
        return EntiteQuerySet(self.model, using=self._db)

    def actifs(self):
        return self.get_queryset().actifs()

    def supprimes(self):
        return self.get_queryset().supprimes()


# ---------------------------------------------------------------------------
# Socle de Traçabilité — abstrait, hérité par TOUTE entité du système
# ---------------------------------------------------------------------------

class SocleTracabilite(models.Model):
    """
    Socle de Traçabilité commun à toute entité, sans exception.

    - Identifiant technique unique, immuable, généré à la création
    - Créé le / Créé par (ou "Système")
    - Modifié le / Modifié par (ou "Système")
    - Version — compteur incrémenté à chaque modification (écritures concurrentes)
    - Statut du cycle de vie — jamais de suppression physique
    - Origine de la donnée
    - Motif de la dernière modification (obligatoire hors création)
    - Suppression logique (Supprimé le / Supprimé par) — la ligne reste en base
    """

    id = models.BigAutoField(
        primary_key=True,
        verbose_name=_('Identifiant technique'),
    )

    # --- Création ---
    cree_le = models.DateTimeField(
        _('Créé le'), auto_now_add=True, db_index=True,
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('Créé par'),
        related_name='%(app_label)s_%(class)s_crees',
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text=_("Laisser vide et renseigner « Créé par (système) » si l'action est automatisée/synchronisée."),
    )
    cree_par_systeme = models.CharField(
        _('Créé par (système)'), max_length=150, blank=True,
        help_text=_("Nom du processus/système automatisé à l'origine de la création."),
    )

    # --- Modification ---
    modifie_le = models.DateTimeField(
        _('Modifié le'), auto_now=True, db_index=True,
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('Modifié par'),
        related_name='%(app_label)s_%(class)s_modifies',
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    modifie_par_systeme = models.CharField(
        _('Modifié par (système)'), max_length=150, blank=True,
    )

    # --- Concurrence & cycle de vie ---
    version = models.PositiveIntegerField(
        _('Version'), default=1,
        help_text=_("Compteur entier incrémenté à chaque modification, pour détecter les écritures concurrentes."),
    )
    statut = models.CharField(
        _('Statut du cycle de vie'), max_length=30,
        choices=StatutCycleVie.choices, default=StatutCycleVie.ACTIF,
        db_index=True,
    )
    origine_donnee = models.CharField(
        _('Origine de la donnée'), max_length=30,
        choices=OrigineDonnee.choices, default=OrigineDonnee.SAISIE_MANUELLE,
    )
    motif_derniere_modification = models.TextField(
        _('Motif de la dernière modification'), blank=True,
        help_text=_('Texte libre, obligatoire dès qu’il ne s’agit pas d’une création.'),
    )

    # --- Suppression logique ---
    supprime_le = models.DateTimeField(_('Supprimé le'), null=True, blank=True)
    supprime_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_('Supprimé par'),
        related_name='%(app_label)s_%(class)s_supprimes',
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    objects = EntiteManager()

    class Meta:
        abstract = True
        get_latest_by = 'modifie_le'

    # -- Comportements communs --------------------------------------------

    def save(self, *args, **kwargs):
        """Incrémente automatiquement la version à chaque modification
        (pas à la création)."""
        if self.pk:
            self.version = (self.version or 1) + 1
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.pk and not self.supprime_le and not self.motif_derniere_modification:
            # Rappel de la règle métier ; volontairement non bloquant ici
            # (certains flux techniques/synchronisés ne passent pas par
            # full_clean()). Les serializers d'API l'appliquent strictement.
            pass

    @property
    def est_supprime(self):
        return self.supprime_le is not None

    def supprimer_logiquement(self, utilisateur=None, systeme=''):
        """Suppression logique : l'enregistrement reste en base, simplement
        invisible dans les usages courants (cf. EntiteManager.actifs())."""
        self.supprime_le = timezone.now()
        self.supprime_par = utilisateur
        if systeme and not utilisateur:
            self.modifie_par_systeme = systeme
        self.save()

    def marquer_modification(self, utilisateur=None, motif='', systeme=''):
        """Helper pour tracer proprement une modification métier."""
        if utilisateur:
            self.modifie_par = utilisateur
        if systeme:
            self.modifie_par_systeme = systeme
        if motif:
            self.motif_derniere_modification = motif
        self.save()


class PeriodeValiditeMixin(models.Model):
    """
    Mixin abstrait pour les entités à caractère temporel
    (« Valide du / Valide au »), précisé entité par entité dans les
    modèles concrets (parfois recopié depuis Date de début/fin métier).
    """
    valide_du = models.DateField(_('Valide du'), null=True, blank=True)
    valide_au = models.DateField(_('Valide au'), null=True, blank=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.valide_du and self.valide_au and self.valide_du > self.valide_au:
            raise ValidationError({'valide_au': _('La date de fin de validité doit être postérieure à la date de début.')})

    def est_valide_a(self, date=None):
        date = date or timezone.now().date()
        if self.valide_du and date < self.valide_du:
            return False
        if self.valide_au and date > self.valide_au:
            return False
        return True

    @property
    def est_valide_aujourdhui(self):
        return self.est_valide_a()


class EntitePolymorphiqueMixin(models.Model):
    """
    Mixin abstrait pour les DEUX SEULES entités du modèle (E2.1 Journal
    d'Événement, E3.2 File de Synchronisation) dont la vocation est de
    référencer, de façon polymorphe et non typée strictement, n'importe
    quelle entité de n'importe quel système (structurel ou métier futur).

    Implémenté via le framework `contenttypes` de Django (GenericForeignKey)
    plutôt qu'une simple paire de champs texte, pour bénéficier d'une
    résolution fiable de l'objet cible tout en restant totalement générique.
    """
    entite_type = models.ForeignKey(
        'contenttypes.ContentType',
        verbose_name=_('Type d’entité référencée'),
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name='+',
    )
    entite_id = models.PositiveBigIntegerField(
        _('Identifiant de l’entité référencée'), null=True, blank=True,
    )
    entite_reference = GenericForeignKey('entite_type', 'entite_id')

    # Repli volontairement non contraint (label libre), pour les cas où la
    # source n'est pas un modèle Django recensé dans ContentType (ex: appel
    # externe, système tiers) — cf. E1.2 Envoi (origine polymorphe).
    systeme_source = models.CharField(
        _('Système source'), max_length=100, blank=True,
        help_text=_("Label souple du système fonctionnel à l'origine de la référence."),
    )

    class Meta:
        abstract = True
