"""
sondages/api/v1/services.py
==============================
"""

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ... import models


def enregistrer_vote(sondage: models.Sondage, utilisateur, choix_ids: list) -> models.Sondage:
    if sondage.statut != models.SondageStatutChoices.ACTIF:
        raise ValidationError("Ce sondage n'est pas actif.")

    maintenant = timezone.now()
    if maintenant < sondage.date_debut or maintenant > sondage.date_fin:
        raise ValidationError("Ce sondage n'est pas ouvert au vote actuellement.")

    if not choix_ids:
        raise ValidationError('Au moins un choix est requis.')

    if sondage.type_vote == models.TypeVoteSondage.UNIQUE and len(choix_ids) > 1:
        raise ValidationError('Ce sondage est à choix unique.')

    choix_valides = list(sondage.choix.filter(pk__in=choix_ids))
    if len(choix_valides) != len(set(choix_ids)):
        raise ValidationError('Un ou plusieurs choix sont invalides pour ce sondage.')

    for choix in choix_valides:
        models.VoteSondage.objects.get_or_create(sondage=sondage, choix=choix, utilisateur=utilisateur)

    return sondage
