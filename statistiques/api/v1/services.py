"""
statistiques/api/v1/services.py
==================================

Calcule `StatistiquesGlobales` (voir src/types/models/statistiques.types.ts
côté frontend) entièrement côté serveur : agrégations SQL (Count, group
by), jamais de données brutes renvoyées au frontend pour qu'il les
recalcule lui-même. C'est le cœur de l'exigence « le backend s'occupe
de tout » pour les statistiques.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from commentaires.models import Commentaire, VoteCommentaire
from news.models import News, NewsStatutChoices, NewsVue
from referentiels.models import Organisation, Categorie
from sondages.models import VoteSondage


def _debut_mois(date):
    return date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def calculer_statistiques_globales() -> dict:
    maintenant = timezone.now()
    debut_mois_courant = _debut_mois(maintenant)
    debut_mois_precedent = _debut_mois(debut_mois_courant - timedelta(days=1))

    news_actives_qs = News.objects.actifs().filter(statut=NewsStatutChoices.PUBLIE)
    total_news_actives = news_actives_qs.count()

    total_votes = VoteSondage.objects.count() + VoteCommentaire.objects.count()
    total_visiteurs = NewsVue.objects.values('utilisateur_id', 'adresse_ip').distinct().count()

    news_ce_mois = News.objects.actifs().filter(cree_le__gte=debut_mois_courant).count()
    news_mois_precedent = News.objects.actifs().filter(
        cree_le__gte=debut_mois_precedent, cree_le__lt=debut_mois_courant,
    ).count()
    croissance_mensuelle = (
        round((news_ce_mois - news_mois_precedent) / news_mois_precedent * 100, 1)
        if news_mois_precedent > 0 else (100.0 if news_ce_mois > 0 else 0.0)
    )

    # Part des News publiées disposant d'au moins un LienPublication (voir
    # liens/models.py) -- le mécanisme d'enregistrement/traçabilité sur le
    # "registre certifié CIVITAS" mis en avant côté frontend
    # (NewsDetailContent.tsx). Ce n'est PAS automatique à la publication
    # (créé via un endpoint dédié, voir LienPublicationEcritureSerializer) :
    # un ratio < 100% est donc possible et significatif, pas un artefact.
    news_avec_lien_publication = news_actives_qs.filter(liens_publication__isnull=False).distinct().count()
    taux_transparence = (
        round(news_avec_lien_publication / total_news_actives * 100, 1) if total_news_actives > 0 else 0.0
    )

    return {
        'total_visiteurs': total_visiteurs,
        'total_votes': total_votes,
        'total_commentaires': Commentaire.objects.actifs().count(),
        'total_news_actives': total_news_actives,
        'total_sujets_actifs': total_news_actives,
        'total_organisations': Organisation.objects.actifs().count(),
        'croissance_mensuelle': croissance_mensuelle,
        'taux_transparence': taux_transparence,
        'participation_par_province': _participation_par_province(),
        'repartition_par_categorie': _repartition_par_categorie(),
        'activite_par_heure': _activite_par_heure(),
    }


def _participation_par_province():
    resultats = []
    news_par_province = (
        News.objects.actifs()
        .exclude(province='')
        .values('province')
        .annotate(nb_news=Count('id', distinct=True))
        .order_by('-nb_news')
    )
    for entree in news_par_province:
        province = entree['province']
        nb_votes = VoteSondage.objects.filter(sondage__news__province=province).count()
        resultats.append({
            'province': province,
            'votes': nb_votes,
            'news': entree['nb_news'],
            'sujets': entree['nb_news'],
        })
    return resultats


def _repartition_par_categorie():
    total = News.objects.actifs().count()
    if total == 0:
        return []

    resultats = []
    categories = Categorie.objects.actifs().annotate(nb_news=Count('news', distinct=True)).filter(nb_news__gt=0)
    for categorie in categories:
        resultats.append({
            'category': categorie.nom,
            'count': categorie.nb_news,
            'percentage': round(categorie.nb_news / total * 100, 1),
        })
    return sorted(resultats, key=lambda item: item['count'], reverse=True)


def _activite_par_heure():
    from django.db.models.functions import ExtractHour

    votes_par_heure = dict(
        VoteSondage.objects.annotate(heure=ExtractHour('cree_le')).values('heure')
        .annotate(total=Count('id')).values_list('heure', 'total')
    )
    commentaires_par_heure = dict(
        Commentaire.objects.actifs().annotate(heure=ExtractHour('cree_le')).values('heure')
        .annotate(total=Count('id')).values_list('heure', 'total')
    )

    return [
        {
            'heure': f'{h:02d}:00',
            'votes': votes_par_heure.get(h, 0),
            'commentaires': commentaires_par_heure.get(h, 0),
        }
        for h in range(24)
    ]
