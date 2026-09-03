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
