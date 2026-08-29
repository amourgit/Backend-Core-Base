"""
news/api/v1/services.py
=========================

Logique métier réutilisable pour le domaine News, indépendante des
vues DRF (appelable depuis les vues, les signaux, une commande de
management, etc.). C'est ici que vivent les "traitements déjà tout
faits et corrects" évoqués pour le backend : génération de slug,
bascule de réaction idempotente, enregistrement de vue, etc.
"""

from django.utils.text import slugify

from ... import models


def generer_slug_unique(titre: str, instance_id=None) -> str:
    base = slugify(titre)[:240] or 'news'
    slug = base
    compteur = 1
    qs = models.News.objects.all()
    if instance_id:
        qs = qs.exclude(pk=instance_id)
    while qs.filter(slug=slug).exists():
        compteur += 1
        slug = f'{base}-{compteur}'
    return slug


def ajouter_reaction(news: models.News, utilisateur, type_reaction: str) -> models.News:
    """Ajoute une réaction sur `news`. Décision produit : aucune contrainte
    d'authentification ni de nombre de réactions -- chaque appel crée une
    nouvelle ligne, `utilisateur` peut être None (visiteur anonyme)."""
    models.ReactionNews.objects.create(news=news, utilisateur=utilisateur, type_reaction=type_reaction)
    return news


def enregistrer_vue(news: models.News, utilisateur, adresse_ip: str = None) -> None:
    """Enregistre une consultation. Évite le survote artificiel des
    statistiques : un même utilisateur authentifié n'incrémente les vues
    qu'une fois par tranche de 30 minutes sur la même News."""
    from django.utils import timezone
    from datetime import timedelta

    if utilisateur and utilisateur.is_authenticated:
        recent = models.NewsVue.objects.filter(
            news=news, utilisateur=utilisateur, horodatage__gte=timezone.now() - timedelta(minutes=30),
        ).exists()
        if recent:
            return
        models.NewsVue.objects.create(news=news, utilisateur=utilisateur, adresse_ip=adresse_ip)
    else:
        models.NewsVue.objects.create(news=news, utilisateur=None, adresse_ip=adresse_ip)


def incrementer_partages(news: models.News) -> int:
    from django.db.models import F
    models.News.objects.filter(pk=news.pk).update(partages=F('partages') + 1)
    news.refresh_from_db(fields=['partages'])
    return news.partages
