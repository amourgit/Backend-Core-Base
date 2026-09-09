"""
adhesions/models.py
====================

Réforme identité globale / adhésion tenant :

- `users.User` est désormais UN SEUL compte, GLOBAL, qui vit UNIQUEMENT
  dans le schéma public (SHARED_APPS). On s'authentifie UNE SEULE
  FOIS, de façon globale -- il n'existe plus de compte dupliqué par
  tenant (`users` a été retiré de TENANT_APPS).
- Ce que `users.User` portait auparavant comme métadonnées propres à UN
  tenant (rôle, organisation, établissement, badges) devient une
  ADHÉSION : une ligne `MembreTenant`, qui vit DANS le schéma du
  tenant (cette app est dans TENANT_APPS), et qui réfère l'utilisateur
  global par simple entier (`user_id`), JAMAIS par ForeignKey Django --
  une contrainte FK physique inter-schémas serait fragile et casserait
  l'isolation (même principe déjà appliqué à `TokenManager.user_id`,
  voir token_manager/models.py).

Un même utilisateur global peut donc avoir zéro, une, ou plusieurs
adhésions (une par tenant dans lequel il est enregistré), chacune avec
son propre rôle/organisation/établissement/badges/statut -- ce qui
permet à une même personne d'être "étudiant" dans un tenant et
"modérateur" dans un autre, avec un seul login.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from common.models import SocleTracabilite


class RoleUtilisateur(models.TextChoices):
    """Rôle applicatif d'un membre AU SEIN D'UN TENANT donné -- pilote les
    permissions frontend fines (voir src/lib/permissions/ côté frontend)
    et backend (voir common/permissions.py). 'anonyme' n'est jamais
    stocké : il ne s'applique qu'aux requêtes non authentifiées, côté
    frontend."""
    ETUDIANT = 'etudiant', _('Étudiant')
    MODERATEUR = 'moderateur', _('Modérateur')
    ADMINISTRATEUR = 'administrateur', _('Administrateur')
    ORGANISATION = 'organisation', _('Organisation')


class StatutAdhesion(models.TextChoices):
    """Cycle de vie de la relation membre <-> tenant."""
    EN_ATTENTE = 'en_attente', _("En attente d'approbation")
    ACCEPTEE = 'acceptee', _('Acceptée')
    REFUSEE = 'refusee', _('Refusée')
    SUSPENDUE = 'suspendue', _('Suspendue')


class Badge(models.Model):
    """Distinction attribuée à un membre PAR ce tenant (référentiel
    simple, propre au tenant -- deux tenants peuvent définir un badge du
    même nom sans lien entre eux)."""
    nom = models.CharField(_('Nom'), max_length=100, unique=True)
    icone = models.CharField(_('Icône'), max_length=10, default='🏅', help_text=_('Emoji ou code icône court.'))
    description = models.CharField(_('Description'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('Badge')
        verbose_name_plural = _('Badges')
        ordering = ['nom']

    def __str__(self):
        return self.nom


class MembreTenantQuerySet(models.QuerySet):
    def actifs(self):
        return self.filter(statut_adhesion=StatutAdhesion.ACCEPTEE, supprime_le__isnull=True)

    def en_attente(self):
        return self.filter(statut_adhesion=StatutAdhesion.EN_ATTENTE, supprime_le__isnull=True)

    def pour_utilisateur(self, user_id):
        return self.filter(user_id=user_id)


class MembreTenantManager(models.Manager.from_queryset(MembreTenantQuerySet)):
    pass


class MembreTenant(SocleTracabilite):
    """
    Représentation, DANS CE TENANT, d'un utilisateur global
    (`users.User`, schéma public). Porte tout ce qui est propre à la
    relation de cet utilisateur avec CE tenant : rôle, organisation,
    établissement, badges, statut d'adhésion.

    `user_id` n'est volontairement PAS une ForeignKey Django (voir
    docstring de module) : c'est un entier simple qui référence
    `users.User.id` dans le schéma PUBLIC. La validité de cette
    référence est garantie applicativement (voir
    adhesions.api.v1.services.AdhesionService), pas par une contrainte
    SQL inter-schémas.
    """
    objects = MembreTenantManager()

    user_id = models.PositiveBigIntegerField(
        _('Utilisateur (identifiant global)'), db_index=True,
        help_text=_("Référence users.User.id dans le schéma public -- volontairement pas une ForeignKey (isolation inter-schémas, voir TokenManager.user_id)."),
    )

    role = models.CharField(
        _('Rôle'), max_length=20, choices=RoleUtilisateur.choices, default=RoleUtilisateur.ETUDIANT, db_index=True,
    )
    etablissement = models.ForeignKey(
        'referentiels.Etablissement', verbose_name=_('Établissement'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='membres',
    )
    organisation = models.ForeignKey(
        'referentiels.Organisation', verbose_name=_('Organisation'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='membres',
        help_text=_('Renseigné si ce membre représente/gère une organisation publiante dans ce tenant.'),
    )
    badges = models.ManyToManyField(Badge, verbose_name=_('Badges'), blank=True, related_name='membres')

    statut_adhesion = models.CharField(
        _("Statut de l'adhésion"), max_length=20,
        choices=StatutAdhesion.choices, default=StatutAdhesion.ACCEPTEE, db_index=True,
    )
    demande_le = models.DateTimeField(_('Demandé le'), auto_now_add=True)
    traitee_le = models.DateTimeField(_('Traitée le'), null=True, blank=True)
    traitee_par_id = models.PositiveBigIntegerField(
        _('Traitée par (identifiant global)'), null=True, blank=True,
        help_text=_("users.User.id (public) du membre ayant accepté/refusé la demande -- même principe que user_id."),
    )
    motif_refus = models.TextField(_('Motif de refus'), blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user_id']),
            models.Index(fields=['role']),
            models.Index(fields=['statut_adhesion']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user_id'], name='adhesions_membretenant_unique_user'),
        ]
        verbose_name = _('Membre du tenant')
        verbose_name_plural = _('Membres du tenant')
        ordering = ['-cree_le']

    def __str__(self):
        return f"membre#{self.user_id} ({self.role})"

    @property
    def est_active(self):
        return self.statut_adhesion == StatutAdhesion.ACCEPTEE and not self.est_supprime
