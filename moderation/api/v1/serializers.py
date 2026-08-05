from rest_framework import serializers

from users.api.v1.serializers import UtilisateurPublicSerializer
from ... import models


class SignalementSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    auteur_signalement = UtilisateurPublicSerializer(read_only=True)
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)

    class Meta:
        model = models.Signalement
        fields = (
            'id', 'type_contenu', 'contenu_id', 'titre_ou_apercu', 'motif', 'description',
            'auteur_signalement', 'statut', 'created_at',
        )


class SignalementEcritureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Signalement
        fields = ('type_contenu', 'contenu_id', 'titre_ou_apercu', 'motif', 'description')
