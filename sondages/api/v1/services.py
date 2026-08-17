"""
sondages/api/v1/services.py
==============================
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ... import models


def enregistrer_vote(sondage: models.Sondage, utilisateur, choix_ids: list) -> models.Sondage:
    """Enregistre le vote de `utilisateur` sur `sondage` comme l'état
    COMPLET et actuel de sa sélection — pas un simple ajout.

    C'est le même idiome de réconciliation que
    `news/api/v1/services.py:basculer_reaction` (un seul point d'écriture
    idempotent, appelé à chaque interaction utilisateur avec sa sélection
    actuelle), étendu au cas multi-valué des sondages :
      - un choix présent dans `choix_ids` mais pas encore voté -> créé ;
      - un choix déjà voté mais absent de `choix_ids` -> retiré ;
      - un choix déjà voté et toujours présent -> inchangé.

    Cela garantit qu'à tout instant, l'ensemble des `VoteSondage` d'un
    utilisateur pour CE sondage correspond exactement à sa sélection la
    plus récente — jamais une accumulation de votes incohérente avec
    `type_vote` (notamment : un sondage à choix UNIQUE ne peut jamais se
    retrouver avec deux votes actifs pour le même utilisateur, même si
    celui-ci vote plusieurs fois de suite pour des choix différents).

    `choix_ids` vide retire intégralement le vote de l'utilisateur sur ce
    sondage (annulation), de façon symétrique et sans endpoint séparé.
    """
    if sondage.statut != models.SondageStatutChoices.ACTIF:
        raise ValidationError("Ce sondage n'est pas actif.")

    maintenant = timezone.now()
    if maintenant < sondage.date_debut or maintenant > sondage.date_fin:
        raise ValidationError("Ce sondage n'est pas ouvert au vote actuellement.")

    # Normalisation : dédoublonnage + comparaison en chaînes (les ids
    # arrivent en string depuis le frontend, voir SONDAGES_ENDPOINTS.vote
    # côté frontend et le commentaire sur SondageEcritureSerializer.id).
    ids_soumis = {str(cid) for cid in choix_ids if str(cid).strip()}

    if ids_soumis and sondage.type_vote == models.TypeVoteSondage.UNIQUE and len(ids_soumis) > 1:
        raise ValidationError('Ce sondage est à choix unique : une seule option est autorisée.')

    ids_choix_valides = {str(pk) for pk in sondage.choix.values_list('pk', flat=True)}
    if not ids_soumis.issubset(ids_choix_valides):
        raise ValidationError('Un ou plusieurs choix sont invalides pour ce sondage.')

    with transaction.atomic():
        # select_for_update verrouille les votes existants de cet
        # utilisateur pour ce sondage le temps de la réconciliation, pour
        # empêcher une double soumission concurrente (ex: double-clic,
        # deux onglets) de produire un état incohérent.
        votes_existants = list(
            models.VoteSondage.objects.select_for_update()
            .filter(sondage=sondage, utilisateur=utilisateur)
        )
        ids_existants = {str(vote.choix_id) for vote in votes_existants}

        ids_a_retirer = ids_existants - ids_soumis
        ids_a_ajouter = ids_soumis - ids_existants

        if ids_a_retirer:
            models.VoteSondage.objects.filter(
                sondage=sondage, utilisateur=utilisateur, choix_id__in=ids_a_retirer,
            ).delete()

        if ids_a_ajouter:
            models.VoteSondage.objects.bulk_create([
                models.VoteSondage(sondage=sondage, choix_id=choix_id, utilisateur=utilisateur)
                for choix_id in ids_a_ajouter
            ])

    return sondage


def retirer_vote(sondage: models.Sondage, utilisateur) -> models.Sondage:
    """Annule intégralement le vote de `utilisateur` sur `sondage`.
    Équivalent explicite de `enregistrer_vote(sondage, utilisateur, [])`."""
    return enregistrer_vote(sondage, utilisateur, [])
