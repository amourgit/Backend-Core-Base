from django.db.models.signals import post_save
from django.dispatch import receiver
from tenants.models import Tenant
from token_manager.models import TokenSettings

# @receiver(post_save, sender=Tenant)
# def create_tenant_token_settings(sender, instance, created, **kwargs):
#     """
#     Crée une configuration de token par défaut lors de la création d'un tenant
#     """
#     if created:
#         TokenSettings.objects.create(
#             tenant=instance,
#             name=f"Configuration par défaut - {instance.name}",
#             access_token_lifetime=5,  # 5 minutes
#             refresh_token_lifetime=1440,  # 24 heures
#             max_tokens_per_user=5,
#             rotate_refresh_tokens=True,
#             blacklist_after_rotation=True,
#             cookie_secure=True,
#             cookie_samesite='Lax',
#             enable_blacklist=True,
#             blacklist_cleanup_after=60,
#             require_https=True,
#             validate_ip=True,
#             validate_user_agent=True,
#             is_active=True
#         ) 