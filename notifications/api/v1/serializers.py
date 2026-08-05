from rest_framework import serializers

from ... import models


class NotificationSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)
    categorie = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(source='cree_le', read_only=True)
    category_tab = serializers.CharField(required=False)

    class Meta:
        model = models.Notification
        fields = (
            'id', 'format', 'titre', 'description', 'categorie', 'lien', 'lu', 'created_at',
            'tag', 'urgente', 'category_tab', 'notice', 'actions',
        )

    def get_categorie(self, obj):
        return {'nom': obj.categorie_nom, 'couleur': obj.categorie_couleur, 'icone': obj.categorie_icone or None}
