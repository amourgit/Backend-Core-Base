from rest_framework import serializers

from referentiels.models import Categorie, Organisation, Etablissement


class CategorieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categorie
        fields = ['id', 'nom', 'couleur', 'icone', 'description', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']


class OrganisationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organisation
        fields = ['id', 'nom', 'logo', 'type', 'description', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']


class EtablissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Etablissement
        fields = ['id', 'nom', 'province', 'statut', 'cree_le', 'modifie_le']
        read_only_fields = ['id', 'cree_le', 'modifie_le']
