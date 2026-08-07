from rest_framework import serializers

from referentiels.models import Categorie, Organisation, Etablissement


class CategorieSerializer(serializers.ModelSerializer):
    # id en chaîne, comme partout ailleurs sur la plateforme (voir
    # UtilisateurPublicSerializer : "tous les identifiants comme des
    # chaînes de façon uniforme"). Sans ce `source='pk'`, ce endpoint
    # autonome renvoyait un id numérique alors que CategorieNesteeSerializer
    # (news/api/v1/serializers.py), qui sérialise le MÊME modèle en tant
    # qu'objet imbriqué dans une News, le fait déjà en chaîne — un même
    # objet aurait donc un id de type différent selon l'endpoint appelé.
    id = serializers.CharField(source='pk', read_only=True)

    class Meta:
        model = Categorie
        fields = ['id', 'nom', 'couleur', 'icone', 'description', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']


class OrganisationSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)  # voir CategorieSerializer ci-dessus

    class Meta:
        model = Organisation
        fields = ['id', 'nom', 'logo', 'type', 'description', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']


class EtablissementSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)  # voir CategorieSerializer ci-dessus

    class Meta:
        model = Etablissement
        fields = ['id', 'nom', 'province', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']
