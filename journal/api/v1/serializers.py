from rest_framework import serializers

from ... import models


class EvenementJournalSerializer(serializers.ModelSerializer):
    """Correspond à `AuditLog` côté frontend : {id, action, utilisateur, cible, horodatage, adresseIP}."""

    id = serializers.CharField(source='pk', read_only=True)
    utilisateur = serializers.SerializerMethodField()
    cible = serializers.CharField(source='cible_libelle', read_only=True)
    horodatage = serializers.DateTimeField(source='cree_le', read_only=True)
    adresse_ip = serializers.CharField(read_only=True)

    class Meta:
        model = models.EvenementJournal
        fields = ('id', 'action', 'utilisateur', 'cible', 'horodatage', 'adresse_ip')

    def get_utilisateur(self, obj):
        if obj.cree_par:
            return obj.cree_par.get_full_name() or obj.cree_par.username
        return obj.cree_par_systeme or 'Système'
