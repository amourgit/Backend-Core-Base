from rest_framework import serializers


class ParticipationProvinceSerializer(serializers.Serializer):
    province = serializers.CharField()
    votes = serializers.IntegerField()
    news = serializers.IntegerField()
    sujets = serializers.IntegerField()


class RepartitionCategorieSerializer(serializers.Serializer):
    category = serializers.CharField()
    count = serializers.IntegerField()
    percentage = serializers.FloatField()


class ActiviteHeureSerializer(serializers.Serializer):
    heure = serializers.CharField()
    votes = serializers.IntegerField()
    commentaires = serializers.IntegerField()


class StatistiquesGlobalesSerializer(serializers.Serializer):
    total_visiteurs = serializers.IntegerField()
    total_votes = serializers.IntegerField()
    total_commentaires = serializers.IntegerField()
    total_news_actives = serializers.IntegerField()
    total_sujets_actifs = serializers.IntegerField()
    total_organisations = serializers.IntegerField()
    croissance_mensuelle = serializers.FloatField()
    taux_transparence = serializers.FloatField()
    participation_par_province = ParticipationProvinceSerializer(many=True)
    repartition_par_categorie = RepartitionCategorieSerializer(many=True)
    activite_par_heure = ActiviteHeureSerializer(many=True)


# ---------------------------------------------------------------------------
# Statistiques PERSONNELLES (page Profil) — voir services.py pour le calcul
# ---------------------------------------------------------------------------

class ContributionsUtilisateurSerializer(serializers.Serializer):
    news = serializers.IntegerField()
    commentaires = serializers.IntegerField()


class InteractionsUtilisateurSerializer(serializers.Serializer):
    reactions_news = serializers.IntegerField()
    reactions_commentaires = serializers.IntegerField()
    votes_sondages = serializers.IntegerField()
    votes_commentaires = serializers.IntegerField()


class EngagementRecuUtilisateurSerializer(serializers.Serializer):
    reactions = serializers.IntegerField()
    commentaires = serializers.IntegerField()
    vues = serializers.IntegerField()


class TopCategorieUtilisateurSerializer(serializers.Serializer):
    id = serializers.CharField()
    nom = serializers.CharField()
    couleur = serializers.CharField()
    icone = serializers.CharField()
    score = serializers.IntegerField()


class FavoriUtilisateurSerializer(serializers.Serializer):
    id = serializers.CharField()
    slug = serializers.CharField()
    titre = serializers.CharField()
    image = serializers.CharField(allow_null=True)
    type = serializers.CharField()
    categorie_nom = serializers.CharField(allow_null=True)
    categorie_couleur = serializers.CharField()
    score_engagement = serializers.IntegerField()


class VoteRecentUtilisateurSerializer(serializers.Serializer):
    sondage_id = serializers.CharField()
    sondage_titre = serializers.CharField()
    news_slug = serializers.CharField(allow_null=True)
    choix = serializers.ListField(child=serializers.CharField())
    date = serializers.DateTimeField()
    statut = serializers.CharField()


class ActiviteRecenteUtilisateurSerializer(serializers.Serializer):
    type = serializers.CharField()
    titre = serializers.CharField()
    extrait = serializers.CharField(allow_blank=True)
    date = serializers.DateTimeField()
    news_slug = serializers.CharField(allow_null=True)


class MesStatistiquesSerializer(serializers.Serializer):
    contributions = ContributionsUtilisateurSerializer()
    interactions = InteractionsUtilisateurSerializer()
    engagement_recu = EngagementRecuUtilisateurSerializer()
    top_categories = TopCategorieUtilisateurSerializer(many=True)
    favoris = FavoriUtilisateurSerializer(many=True)
    votes_recents = VoteRecentUtilisateurSerializer(many=True)
    activite_recente = ActiviteRecenteUtilisateurSerializer(many=True)
