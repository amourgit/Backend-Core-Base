from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
import re
from django.core.exceptions import ValidationError


class RoleUtilisateur(models.TextChoices):
    """Rôle applicatif de l'utilisateur — pilote les permissions frontend
    fines (voir src/lib/permissions/ côté frontend) et backend
    (voir common/permissions.py). 'anonyme' n'est jamais stocké : il ne
    s'applique qu'aux requêtes non authentifiées, côté frontend."""
    ETUDIANT = 'etudiant', _('Étudiant')
    MODERATEUR = 'moderateur', _('Modérateur')
    ADMINISTRATEUR = 'administrateur', _('Administrateur')
    ORGANISATION = 'organisation', _('Organisation')


class Badge(models.Model):
    """Distinction attribuée à un utilisateur (référentiel simple, peu volatil)."""
    nom = models.CharField(_('Nom'), max_length=100, unique=True)
    icone = models.CharField(_('Icône'), max_length=10, default='🏅', help_text=_('Emoji ou code icône court.'))
    description = models.CharField(_('Description'), max_length=255, blank=True)

    class Meta:
        verbose_name = _('Badge')
        verbose_name_plural = _('Badges')
        ordering = ['nom']

    def __str__(self):
        return self.nom


class User(AbstractUser):
    """
    Custom user model.
    Each instance is automatically isolated in the tenant's schema.
    """
    phone_number = models.CharField(_('Phone number'), max_length=20, blank=True)
    address = models.TextField(_('Address'), blank=True)
    profile_picture = models.ImageField(_('Profile picture'), upload_to='profile_pictures/', blank=True, null=True)
    date_of_birth = models.DateField(_('Date of birth'), null=True, blank=True)
    is_verified = models.BooleanField(_('Verified'), default=False)
    last_login_ip = models.GenericIPAddressField(_('Last login IP'), null=True, blank=True)
    language_preference = models.CharField(_('Preferred language'), max_length=10, default='en')
    timezone = models.CharField(_('Timezone'), max_length=50, default='UTC')

    # --- Champs applicatifs CIVITAS NEWS ---
    role = models.CharField(
        _('Rôle'), max_length=20, choices=RoleUtilisateur.choices, default=RoleUtilisateur.ETUDIANT, db_index=True,
    )
    etablissement = models.ForeignKey(
        'referentiels.Etablissement', verbose_name=_('Établissement'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='utilisateurs',
    )
    organisation = models.ForeignKey(
        'referentiels.Organisation', verbose_name=_('Organisation'),
        null=True, blank=True, on_delete=models.SET_NULL, related_name='membres',
        help_text=_('Renseigné si le compte représente/gère une organisation publiante.'),
    )
    badges = models.ManyToManyField(Badge, verbose_name=_('Badges'), blank=True, related_name='utilisateurs')

    class Meta:
        indexes = [
           models.Index(fields=['username']),
           models.Index(fields=['email']),
           models.Index(fields=['is_active']),
           models.Index(fields=['role']),
        ]
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['username']

    def __str__(self):
        return self.username

    def get_full_name(self):
        """
        Returns the user's full name.
        """
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip() or self.username

    def save(self, *args, **kwargs):
        """
        Override save method to handle tenant.
        """
        # if not self.pk and hasattr(self, '_tenant'):
        #     # If it's a new instance and a tenant has been set
        #     self.tenant = self._tenant
        super().save(*args, **kwargs)
    
    def clean(self):
       super().clean()
       if self.phone_number:
           # Validate phone number format
           if not re.match(r'^\+?1?\d{9,15}$', self.phone_number):
               raise ValidationError(_('Invalid phone number format'))
