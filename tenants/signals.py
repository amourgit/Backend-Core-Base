"""
Signaux Django pour gérer l'invalidation automatique du cache de résolution des tenants
À placer dans tenants/signals.py ou core/signals.py
"""
from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings
from tenants.models import Tenant
import logging

logger = logging.getLogger(__name__)


@receiver([post_save, post_delete], sender=Tenant)
def clear_tenant_cache_on_change(sender, instance, **kwargs):
    """
    Invalide le cache de résolution tenant lors de modifications/suppressions
    """
    try:
        # Construction des clés de cache à invalider
        cache_keys_to_clear = []
        
        # Cache par sous-domaine
        if instance.sous_domaine and settings.MAIN_DOMAIN:
            subdomain_hostname = f"{instance.sous_domaine}.{settings.MAIN_DOMAIN}"
            cache_keys_to_clear.append(f"tenant_resolution:{subdomain_hostname}")
        
        # Cache par domaines associés (si relations ManyToMany avec des domaines)
        if hasattr(instance, 'domains'):
            for domain_obj in instance.domains.all():
                if hasattr(domain_obj, 'domain'):
                    cache_keys_to_clear.append(f"tenant_resolution:{domain_obj.domain}")
        
        # Suppression des clés de cache
        if cache_keys_to_clear:
            cache.delete_many(cache_keys_to_clear)
            logger.info(f"[TenantCache] Cache invalidé pour tenant '{instance.name}': {cache_keys_to_clear}")
        
    except Exception as e:
        logger.error(f"[TenantCache] Erreur lors de l'invalidation du cache pour tenant '{instance.name}': {str(e)}")


@receiver(m2m_changed, sender=Tenant.domains.through)
def clear_tenant_cache_on_domain_change(sender, instance, action, pk_set, **kwargs):
    """
    Invalide le cache lors de modifications des domaines associés au tenant
    Géré via signal m2m_changed pour les relations ManyToMany
    """
    if action in ['post_add', 'post_remove', 'post_clear']:
        try:
            cache_keys_to_clear = []
            
            # Si on a des PKs de domaines modifiés
            if pk_set and hasattr(instance.domains, 'model'):
                Domain = instance.domains.model
                for domain_pk in pk_set:
                    try:
                        domain_obj = Domain.objects.get(pk=domain_pk)
                        if hasattr(domain_obj, 'domain'):
                            cache_keys_to_clear.append(f"tenant_resolution:{domain_obj.domain}")
                    except Domain.DoesNotExist:
                        continue
            
            # Cache par sous-domaine du tenant
            if instance.sous_domaine and settings.MAIN_DOMAIN:
                subdomain_hostname = f"{instance.sous_domaine}.{settings.MAIN_DOMAIN}"
                cache_keys_to_clear.append(f"tenant_resolution:{subdomain_hostname}")
            
            if cache_keys_to_clear:
                cache.delete_many(cache_keys_to_clear)
                logger.info(f"[TenantCache] Cache invalidé après modification domaines pour tenant '{instance.name}': {cache_keys_to_clear}")
                
        except Exception as e:
            logger.error(f"[TenantCache] Erreur lors de l'invalidation du cache domaines pour tenant '{instance.name}': {str(e)}")


def invalidate_tenant_cache_manual(tenant_name_or_hostname):
    """
    Fonction utilitaire pour invalider manuellement le cache d'un tenant
    Useful pour les tâches admin ou de maintenance
    
    Args:
        tenant_name_or_hostname: Nom du tenant ou hostname complet
    """
    try:
        cache_key = f"tenant_resolution:{tenant_name_or_hostname}"
        if cache.delete(cache_key):
            logger.info(f"[TenantCache] Cache invalidé manuellement pour : {tenant_name_or_hostname}")
            return True
        else:
            logger.warning(f"[TenantCache] Aucune clé de cache trouvée pour : {tenant_name_or_hostname}")
            return False
    except Exception as e:
        logger.error(f"[TenantCache] Erreur lors de l'invalidation manuelle : {str(e)}")
        return False


def clear_all_tenant_cache():
    """
    Fonction pour vider tout le cache de résolution des tenants
    Useful pour maintenance ou reset complet
    """
    try:
        # Django ne permet pas de supprimer par pattern, donc on doit lister les clés
        # Alternative : utiliser cache.clear() mais ça vide TOUT le cache
        
        # Version avec cache Redis/Memcached qui supporte les patterns
        if hasattr(cache, 'delete_pattern'):
            deleted = cache.delete_pattern("tenant_resolution:*")
            logger.info(f"[TenantCache] {deleted} clés de cache tenant supprimées")
            return True
        else:
            # Fallback : log l'action mais ne peut pas supprimer par pattern
            logger.warning("[TenantCache] Cache backend ne supporte pas delete_pattern. Utilisez cache.clear() avec précaution.")
            return False
            
    except Exception as e:
        logger.error(f"[TenantCache] Erreur lors du nettoyage complet du cache : {str(e)}")
        return False