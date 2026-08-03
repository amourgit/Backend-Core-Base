from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta

User = get_user_model()


class TokenSettings(models.Model):
    """
    Configuration globale des paramètres de sécurité des tokens
    """
    name = models.CharField(max_length=100, unique=True)
    
    # Durée de vie des tokens
    access_token_lifetime = models.IntegerField(default=5, help_text="Durée de vie du token d'accès en minutes")
    refresh_token_lifetime = models.IntegerField(default=1440, help_text="Durée de vie du token de rafraîchissement en minutes")
    
    # Sécurité
    max_tokens_per_user = models.IntegerField(default=5, help_text="Nombre maximum de tokens actifs par utilisateur")
    rotate_refresh_tokens = models.BooleanField(default=True, help_text="Générer un nouveau token de rafraîchissement à chaque utilisation")
    blacklist_after_rotation = models.BooleanField(default=True, help_text="Mettre en liste noire les anciens tokens après rotation")
    
    # Cookies
    cookie_secure = models.BooleanField(default=True, help_text="Cookies uniquement en HTTPS")
    cookie_samesite = models.CharField(max_length=10, default='Lax', choices=[
        ('Lax', 'Lax'),
        ('Strict', 'Strict'),
        ('None', 'None')
    ])
    cookie_domain = models.CharField(max_length=255, null=True, blank=True)
    
    # Sécurité avancée
    enable_blacklist = models.BooleanField(default=True, help_text="Activer la liste noire des tokens")
    blacklist_cleanup_after = models.IntegerField(default=60, help_text="Nettoyer la liste noire après X minutes")
    require_https = models.BooleanField(default=True, help_text="Exiger HTTPS pour les tokens")
    validate_ip = models.BooleanField(default=True, help_text="Valider l'IP de l'utilisateur")
    validate_user_agent = models.BooleanField(default=True, help_text="Valider le User-Agent")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration de token"
        verbose_name_plural = "Configurations de tokens"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} (Active: {self.is_active})"

    def to_jwt_settings(self):
        """
        Convertit les paramètres en format compatible avec SimpleJWT
        """
        return {
            'ACCESS_TOKEN_LIFETIME': timedelta(minutes=self.access_token_lifetime),
            'REFRESH_TOKEN_LIFETIME': timedelta(minutes=self.refresh_token_lifetime),
            'ROTATE_REFRESH_TOKENS': self.rotate_refresh_tokens,
            'BLACKLIST_AFTER_ROTATION': self.blacklist_after_rotation,
            'UPDATE_LAST_LOGIN': True,
            'ALGORITHM': 'HS256',
            'SIGNING_KEY': settings.SECRET_KEY,
            'VERIFYING_KEY': None,
            'AUTH_HEADER_TYPES': ('Bearer',),
            'USER_ID_FIELD': 'id',
            'USER_ID_CLAIM': 'user_id',
            'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
            'TOKEN_TYPE_CLAIM': 'token_type',
        }

    @classmethod
    def get_active_settings(cls):
        """
        Récupère les paramètres actifs globaux
        """
        return cls.objects.filter(is_active=True).first()


class TokenManager(models.Model):
    """
    Gestion globale des tokens JWT
    """
    user_id = models.IntegerField()
    username = models.CharField(max_length=255)
    tenant_id = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    # Device Information
    device_id = models.CharField(max_length=64, null=True, blank=True)
    device_family = models.CharField(max_length=100, null=True, blank=True)
    device_brand = models.CharField(max_length=100, null=True, blank=True)
    device_model = models.CharField(max_length=100, null=True, blank=True)
    device_type = models.CharField(max_length=20, choices=[
        ('mobile', 'Mobile'),
        ('tablet', 'Tablet'),
        ('desktop', 'Desktop'),
        ('other', 'Other')
    ])
    os_family = models.CharField(max_length=100, null=True, blank=True)
    browser_family = models.CharField(max_length=100, null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    is_current = models.BooleanField(default=False)
    last_used = models.DateTimeField(auto_now=True)
    
    # New fields
    access_token = models.TextField(null=True, blank=True)
    refresh_token = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'token_manager'
        indexes = [
            models.Index(fields=['user_id', 'tenant_id']),
            models.Index(fields=['device_id']),
            models.Index(fields=['is_revoked']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"Token for {self.username} on {self.tenant_id} ({self.device_type})"

    def is_valid(self):
        return not self.is_revoked and self.expires_at > timezone.now()

    def get_device_info(self):
        """Retourne les informations détaillées du device"""
        return {
            'device_id': self.device_id,
            'device_family': self.device_family,
            'device_brand': self.device_brand,
            'device_model': self.device_model,
            'device_type': self.device_type,
            'os_family': self.os_family,
            'browser_family': self.browser_family,
            'location': self.location,
            'ip_address': self.ip_address,
            'last_used': self.last_used,
            'is_current': self.is_current
        }

    def mark_as_current(self):
        """Marque ce token comme la session courante"""
        # Désactive is_current pour toutes les autres sessions de cet utilisateur
        TokenManager.objects.filter(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            is_current=True
        ).exclude(id=self.id).update(is_current=False)
        self.is_current = True
        self.save(update_fields=['is_current'])

    def update_last_used(self):
        """Met à jour le timestamp de dernière utilisation"""
        self.last_used = timezone.now()
        self.save(update_fields=['last_used'])

    def revoke(self):
        """
        Révoque le token
        """
        self.is_revoked = True
        self.is_current = False
        self.revoked_at = timezone.now()
        self.save(update_fields=['is_revoked', 'revoked_at', 'is_current'])

    def renew(self):
       if not self.is_revoked:
           self.expires_at = timezone.now() + timezone.timedelta(minutes=5)
           self.save()
           return True
       return False
