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

from commentaires.models import Commentaire, ReactionCommentaire, VoteCommentaire
from news.models import News, NewsStatutChoices, NewsVue, ReactionNews, TypeReaction
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


# ---------------------------------------------------------------------------
# Statistiques PERSONNELLES (page Profil) — GET /statistiques/v1/moi/
# ---------------------------------------------------------------------------
#
# Distinctes de `calculer_statistiques_globales` (plateforme entière) et
# volontairement PAS ajoutées à `UtilisateurPublicSerializer.get_stats()`
# (users/api/v1/serializers.py:UtilisateurPublicSerializer) : ce serializer
# est imbriqué tel quel dans news.auteur / commentaire.auteur / etc. — une
# agrégation aussi riche y créerait un N+1 sur CHAQUE auteur affiché dans
# toute l'app, pas seulement sur la page Profil. Ici : un seul utilisateur
# (celui de la requête courante), un seul appel, mis en cache comme les
# statistiques globales (voir MesStatistiquesView).

def calculer_statistiques_utilisateur(user, request=None) -> dict:
    contributions_news = News.objects.actifs().filter(auteur=user)
    contributions_commentaires = Commentaire.objects.actifs().filter(auteur=user)

    reactions_news_donnees = ReactionNews.objects.filter(utilisateur=user)
    reactions_commentaires_donnees = ReactionCommentaire.objects.filter(utilisateur=user)
    votes_sondages_donnes = VoteSondage.objects.filter(utilisateur=user)
    votes_commentaires_donnes = VoteCommentaire.objects.filter(utilisateur=user)

    # Engagement REÇU sur le contenu de l'utilisateur (distinct des
    # interactions qu'IL a lui-même données ci-dessus) : ses News et ses
    # commentaires vus par les autres.
    reactions_recues = (
        ReactionNews.objects.filter(news__auteur=user).count()
        + ReactionCommentaire.objects.filter(commentaire__auteur=user).count()
    )
    commentaires_recus = (
        Commentaire.objects.actifs().filter(news__auteur=user).exclude(auteur=user).count()
    )
    vues_recues = NewsVue.objects.filter(news__auteur=user).count()

    return {
        'contributions': {
            'news': contributions_news.count(),
            'commentaires': contributions_commentaires.count(),
        },
        'interactions': {
            'reactions_news': reactions_news_donnees.count(),
            'reactions_commentaires': reactions_commentaires_donnees.count(),
            # Sondages DISTINCTS auxquels l'utilisateur a participé — pas le
            # nombre brut de lignes VoteSondage (un sondage à choix multiple
            # produit une ligne par choix sélectionné, voir
            # sondages/models.py:VoteSondage).
            'votes_sondages': votes_sondages_donnes.values('sondage_id').distinct().count(),
            'votes_commentaires': votes_commentaires_donnes.count(),
        },
        'engagement_recu': {
            'reactions': reactions_recues,
            'commentaires': commentaires_recus,
            'vues': vues_recues,
        },
        'top_categories': _top_categories_utilisateur(user),
        'favoris': _favoris_utilisateur(user, request=request),
        'votes_recents': _votes_recents_utilisateur(user),
        'activite_recente': _activite_recente_utilisateur(user),
    }


def _top_categories_utilisateur(user, limite=5):
    """Catégories (referentiels.Categorie) des News avec lesquelles
    l'utilisateur a un lien quelconque (auteur, commentateur, réacteur, ou
    votant sur un sondage rattaché) — équivalent civique des « genres
    préférés », déduit de l'usage réel plutôt que déclaré."""
    news_touchees = set()
    news_touchees.update(News.objects.actifs().filter(auteur=user).values_list('id', flat=True))
    news_touchees.update(
        Commentaire.objects.actifs().filter(auteur=user).values_list('news_id', flat=True)
    )
    news_touchees.update(ReactionNews.objects.filter(utilisateur=user).values_list('news_id', flat=True))
    news_touchees.update(
        VoteSondage.objects.filter(utilisateur=user).values_list('sondage__news_id', flat=True)
    )
    news_touchees.discard(None)

    if not news_touchees:
        return []

    categories = (
        Categorie.objects.actifs()
        .filter(news__id__in=news_touchees)
        .annotate(score=Count('news', filter=Q(news__id__in=news_touchees), distinct=True))
        .filter(score__gt=0)
        .order_by('-score')[:limite]
    )
    return [
        {'id': str(cat.pk), 'nom': cat.nom, 'couleur': cat.couleur, 'icone': cat.icone, 'score': cat.score}
        for cat in categories
    ]


def _serialiser_favori(news, request=None):
    image_url = None
    if news.image:
        image_url = request.build_absolute_uri(news.image.url) if request else news.image.url
    return {
        'id': str(news.pk),
        'slug': news.slug,
        'titre': news.titre,
        'image': image_url,
        'type': news.type,
        'categorie_nom': news.categorie.nom if news.categorie_id else None,
        'categorie_couleur': news.categorie.couleur if news.categorie_id else '#5B4DFF',
        # « Score » façon note communautaire (voir FavoriUtilisateurSerializer)
        # -- nombre total de réactions reçues par cette News, tous types
        # confondus, calculé à la volée (jamais de compteur dénormalisé).
        'score_engagement': news.reactions.count(),
    }


def _favoris_utilisateur(user, request=None, limite=8):
    """News que l'utilisateur a « cœurées » (ReactionNews de type COEUR) —
    équivalent civique des contenus mis en favori. Une réaction n'étant PAS
    unique par utilisateur (voir news/models.py:ReactionNews), on déduplique
    par News en Python en parcourant du plus récent au plus ancien, sur le
    même modèle que NewsListSerializer.get_reacteurs_recents."""
    news_vues = set()
    favoris = []
    reactions = (
        ReactionNews.objects.filter(utilisateur=user, type_reaction=TypeReaction.COEUR)
        .select_related('news', 'news__categorie')
        .order_by('-cree_le')
    )
    for reaction in reactions:
        news = reaction.news
        if news is None or news.id in news_vues:
            continue
        if news.supprime_le is not None or news.statut != NewsStatutChoices.PUBLIE:
            continue
        news_vues.add(news.id)
        favoris.append(_serialiser_favori(news, request=request))
        if len(favoris) >= limite:
            break
    return favoris


def _votes_recents_utilisateur(user, limite=6):
    """Votes de sondages regroupés PAR sondage (un choix multiple produit
    plusieurs lignes VoteSondage pour un même sondage — voir
    sondages/models.py) — la date retenue par sondage est celle de sa
    première occurrence dans ce flux trié par date décroissante, donc son
    vote le plus récent."""
    votes = (
        VoteSondage.objects.filter(utilisateur=user)
        .select_related('sondage', 'sondage__news', 'choix')
        .order_by('-cree_le')
    )
    par_sondage = {}
    ordre_sondages = []
    for vote in votes:
        sondage_id = vote.sondage_id
        if sondage_id not in par_sondage:
            par_sondage[sondage_id] = {'sondage': vote.sondage, 'choix': [], 'date': vote.cree_le}
            ordre_sondages.append(sondage_id)
        par_sondage[sondage_id]['choix'].append(vote.choix.libelle)

    resultats = []
    for sondage_id in ordre_sondages[:limite]:
        entree = par_sondage[sondage_id]
        sondage = entree['sondage']
        resultats.append({
            'sondage_id': str(sondage.pk),
            'sondage_titre': sondage.titre,
            'news_slug': sondage.news.slug if sondage.news_id else None,
            'choix': entree['choix'],
            'date': entree['date'],
            'statut': sondage.statut,
        })
    return resultats


def _activite_recente_utilisateur(user, limite=10):
    """Fusionne les 4 types d'actions civiques de l'utilisateur (commentaire,
    réaction, vote, publication) triées par date décroissante — chaque type
    est requêté séparément (modèles distincts, pas d'UNION SQL simple) puis
    fusionné/trié côté Python, volontairement borné à `limite` par type en
    amont pour ne jamais charger tout l'historique d'un utilisateur actif."""
    evenements = []

    for commentaire in (
        Commentaire.objects.actifs().filter(auteur=user).select_related('news').order_by('-cree_le')[:limite]
    ):
        evenements.append({
            'type': 'commentaire',
            'titre': commentaire.news.titre if commentaire.news_id else '',
            'extrait': commentaire.contenu[:140],
            'date': commentaire.cree_le,
            'news_slug': commentaire.news.slug if commentaire.news_id else None,
        })

    for reaction in (
        ReactionNews.objects.filter(utilisateur=user).select_related('news').order_by('-cree_le')[:limite]
    ):
        if reaction.news_id is None:
            continue
        evenements.append({
            'type': 'reaction',
            'titre': reaction.news.titre,
            'extrait': reaction.get_type_reaction_display(),
            'date': reaction.cree_le,
            'news_slug': reaction.news.slug,
        })

    for vote in (
        VoteSondage.objects.filter(utilisateur=user)
        .select_related('sondage', 'sondage__news', 'choix')
        .order_by('-cree_le')[:limite]
    ):
        evenements.append({
            'type': 'vote',
            'titre': vote.sondage.titre,
            'extrait': vote.choix.libelle,
            'date': vote.cree_le,
            'news_slug': vote.sondage.news.slug if vote.sondage.news_id else None,
        })

    for news in (
        News.objects.actifs().filter(auteur=user, statut=NewsStatutChoices.PUBLIE).order_by('-cree_le')[:limite]
    ):
        evenements.append({
            'type': 'publication',
            'titre': news.titre,
            'extrait': news.description[:140],
            'date': news.cree_le,
            'news_slug': news.slug,
        })

    evenements.sort(key=lambda evenement: evenement['date'], reverse=True)
    return evenements[:limite]
