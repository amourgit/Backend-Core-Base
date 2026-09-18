"""
Signaux Django : invalidation du cache de résolution tenant
(tenants/middleware.py::_resolve_tenant_with_cache) à chaque
création/modification/suppression d'un Tenant ou d'un Domain.

Câblé depuis TenantsConfig.ready() (tenants/apps.py) -- avant ce
correctif, ce module existait déjà mais n'était importé nulle part
(ready() commenté), ET le récepteur domaines utilisait
`sender=Tenant.domains.through`, qui n'existe PAS : `Domain.tenant`
est un ForeignKey classique (voir domain/models.py), pas un
ManyToManyField -- `Tenant.domains` n'a donc jamais eu de `.through`,
cette ligne aurait levé une AttributeError au chargement si jamais
elle avait été importée. Double raison pour laquelle l'invalidation
n'a jamais eu lieu en pratique : signal jamais câblé, ET l'aurait été
cassé de toute façon. Remplacé ci-dessous par un récepteur direct sur
le VRAI modèle Domain (domain.models.Domain).

Conséquence concrète de cette absence : un Tenant recréé avec le même
sous-domaine après suppression (fréquent en itérant sur la création
self-service), ou un Domain modifié/ajouté après coup, restait résolu
par le cache vers l'ancienne valeur (ou "introuvable") jusqu'à
expiration du TTL -- un tenant qui semble "figé" côté frontend malgré
un en-tête X-Tenant-Domain recalculé correctement à chaque requête
(store/tenants.store.ts, déjà correct de ce côté).
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.conf import settings
from tenants.models import Tenant
from domain.models import Domain
import logging

logger = logging.getLogger(__name__)


def invalidate_tenant_resolution_cache(sous_domaine=None, domains=None):
    """
    Point d'entrée UNIQUE pour invalider tenants/middleware.py::
    _resolve_tenant_with_cache -- utilisé par les récepteurs ci-dessous
    ET par tout code qui mute un Tenant sans passer par `.save()`/
    `.delete()` (donc sans déclencher post_save/post_delete), par ex.
    un `.update()` sur queryset -- voir bulk_activate_tenants /
    bulk_deactivate_tenants dans tenants/api/v1/services.py.

    `sous_domaine` : sous-domaine COURT du tenant (pas le hostname
    complet) -- reconstruit ici en `<sous_domaine>.<MAIN_DOMAIN>`,
    seule forme sous laquelle ce hostname est jamais mis en cache
    (voir _resolve_tenant / le hostname passé à _resolve_tenant_with_cache).
    `domains` : liste de hostnames COMPLETS (Domain.domain), déjà sous
    la forme exacte utilisée comme clé de cache.
    """
    cache_keys = []
    if sous_domaine and settings.MAIN_DOMAIN:
        cache_keys.append(f"tenant_resolution:{sous_domaine}.{settings.MAIN_DOMAIN}")
    for domain_value in (domains or []):
        cache_keys.append(f"tenant_resolution:{domain_value}")
    if cache_keys:
        cache.delete_many(cache_keys)
    return cache_keys


@receiver([post_save, post_delete], sender=Tenant)
def clear_tenant_cache_on_tenant_change(sender, instance, **kwargs):
    """
    Invalide le cache par SOUS-DOMAINE à chaque sauvegarde/suppression
    d'un Tenant. Ne touche PAS aux Domain associés ici : en cascade sur
    une suppression, les lignes Domain sont déjà supprimées (et leur
    propre signal post_delete déjà passé) avant que ce récepteur ne
    s'exécute -- `instance.domains.all()` y renverrait un queryset vide,
    donnant l'illusion à tort qu'il n'y a rien à invalider. Voir le
    récepteur dédié ci-dessous, sur le modèle Domain lui-même.
    """
    try:
        keys = invalidate_tenant_resolution_cache(sous_domaine=instance.sous_domaine)
        if keys:
            logger.info(f"[TenantCache] Invalidé pour tenant '{instance.name}': {keys}")
    except Exception:
        logger.error(f"[TenantCache] Échec invalidation pour tenant '{instance.name}'", exc_info=True)


@receiver([post_save, post_delete], sender=Domain)
def clear_tenant_cache_on_domain_change(sender, instance, **kwargs):
    """
    Invalide le cache pour LE domaine complet créé/modifié/supprimé.
    `instance.domain` reste renseigné sur l'instance Python même en
    post_delete (valeur lue avant suppression SQL) -- fonctionne donc
    pour les 3 cas (création, édition, suppression), y compris en
    cascade depuis la suppression d'un Tenant (ce récepteur s'exécute
    AVANT le post_delete du Tenant parent, voir le Collector Django).
    """
    try:
        keys = invalidate_tenant_resolution_cache(domains=[instance.domain])
        if keys:
            logger.info(f"[TenantCache] Invalidé pour domaine '{instance.domain}': {keys}")
    except Exception:
        logger.error(f"[TenantCache] Échec invalidation pour domaine '{instance.domain}'", exc_info=True)


def clear_all_tenant_cache():
    """
    Vide tout le cache de résolution tenant -- maintenance/reset manuel
    uniquement (ex: shell Django). Ne dépend pas de `delete_pattern`
    (absent de LocMemCache, présent avec django-redis) : reconstruit la
    liste exacte des clés depuis la base plutôt que de scanner le cache.
    """
    try:
        cache_keys = []
        for tenant in Tenant.objects.all():
            if tenant.sous_domaine and settings.MAIN_DOMAIN:
                cache_keys.append(f"tenant_resolution:{tenant.sous_domaine}.{settings.MAIN_DOMAIN}")
        for domain_obj in Domain.objects.all():
            cache_keys.append(f"tenant_resolution:{domain_obj.domain}")
        if cache_keys:
            cache.delete_many(cache_keys)
        logger.info(f"[TenantCache] {len(cache_keys)} clés invalidées (reset complet).")
        return len(cache_keys)
    except Exception:
        logger.error("[TenantCache] Échec du nettoyage complet du cache", exc_info=True)
        return 0
