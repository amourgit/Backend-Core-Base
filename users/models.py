from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
import re
from django.core.exceptions import ValidationError


class User(AbstractUser):
    """
    Compte GLOBAL, unique, vivant UNIQUEMENT dans le schéma public
    (`users` n'est plus listé que dans SHARED_APPS -- voir
    config/settings.py). On s'authentifie une seule fois, de façon
    globale : ce modèle ne porte plus aucune métadonnée propre à un
    tenant particulier.

    Le rôle applicatif, l'organisation/établissement de rattachement et
    les badges -- propres à CHAQUE tenant dans lequel cette personne
    est enregistrée -- vivent désormais dans `adhesions.MembreTenant`
    (une ligne par tenant, dans le schéma de ce tenant, référençant cet
    utilisateur par `user_id` simple, jamais par ForeignKey physique --
    voir adhesions/models.py pour le détail et la justification).
    """
    # `email`/`phone_number` doivent être uniques (nullable pour laisser
    # les deux optionnels indépendamment l'un de l'autre : un compte créé
    # avec un téléphone peut ne pas avoir d'email et vice-versa) -- ce
    # sont les deux SEULS identifiants de connexion possibles côté
    # frontend (voir LoginPage.tsx : un unique champ "identifiant"),
    # donc une valeur non-unique casserait la garantie "au plus un
    # compte par identifiant" sur laquelle repose toute la logique de
    # recherche dans UsersService.get_user_by_identifiant().
    email = models.EmailField(_('email address'), max_length=254, unique=True, null=True, blank=True)
    phone_number = models.CharField(_('Phone number'), max_length=20, unique=True, null=True, blank=True)
    address = models.TextField(_('Address'), blank=True)
    profile_picture = models.ImageField(_('Profile picture'), upload_to='profile_pictures/', blank=True, null=True)
    date_of_birth = models.DateField(_('Date of birth'), null=True, blank=True)
    is_verified = models.BooleanField(_('Verified'), default=False)
    last_login_ip = models.GenericIPAddressField(_('Last login IP'), null=True, blank=True)
    language_preference = models.CharField(_('Preferred language'), max_length=10, default='en')
    timezone = models.CharField(_('Timezone'), max_length=50, default='UTC')

    class Meta:
        indexes = [
           models.Index(fields=['username']),
           models.Index(fields=['email']),
           models.Index(fields=['is_active']),
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
        # Normalise '' -> None pour email/phone_number : ce sont les deux
        # SEULS identifiants de connexion (voir
        # UsersService.get_user_by_identifiant) et donc UNIQUES en base --
        # une chaîne vide partagée par plusieurs comptes violerait cette
        # contrainte dès le second compte sans email/téléphone renseigné.
        # PostgreSQL ne traite JAMAIS deux valeurs '' comme distinctes sous
        # une contrainte unique, contrairement à deux NULL. Fait ICI (au
        # niveau du modèle, pas dans un serializer) pour protéger TOUTES
        # les voies de création d'utilisateur de façon uniforme --
        # RegisterView/GoogleAuthView (token_manager), UserViewSet admin
        # (UserCreateSerializer, qui ne fournit même pas phone_number),
        # `createsuperuser`, l'admin Django... pas seulement le nouveau
        # flux d'inscription simplifié.
        if self.email == '':
            self.email = None
        if self.phone_number == '':
            self.phone_number = None
        super().save(*args, **kwargs)

    def clean(self):
       super().clean()
       if self.phone_number:
           # Validate phone number format
           if not re.match(r'^\+?1?\d{9,15}$', self.phone_number):
               raise ValidationError(_('Invalid phone number format'))
