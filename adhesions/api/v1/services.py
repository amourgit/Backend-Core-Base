"""
adhesions/api/v1/services.py
=============================

Point d'entrée unique pour résoudre "qui est ce user_id global DANS le
tenant courant" -- utilisé par common/permissions.py (rôle) et par les
serializers qui exposent role/organisation/etablissement/badges d'un
auteur (UtilisateurPublicSerializer, etc.).

Toujours appelé implicitement DANS le schema_context du tenant actif
(pas de paramètre tenant : c'est la connexion DB courante qui décide).
"""
from django.db import transaction

from adhesions.models import MembreTenant, RoleUtilisateur, StatutAdhesion


class AdhesionService:

    @staticmethod
    def get_membre(user_id):
        """MembreTenant de `user_id` dans le tenant courant, ou None."""
        if not user_id:
            return None
        return (
            MembreTenant.objects
            .select_related('etablissement', 'organisation')
            .prefetch_related('badges')
            .filter(user_id=user_id)
            .first()
        )

    @staticmethod
    def get_membres_map(user_ids):
        """Version bulk de get_membre -- évite le N+1 quand on sérialise
        une liste (news, commentaires, ...). Retourne {user_id: MembreTenant}."""
        ids = {uid for uid in user_ids if uid}
        if not ids:
            return {}
        membres = (
            MembreTenant.objects
            .select_related('etablissement', 'organisation')
            .prefetch_related('badges')
            .filter(user_id__in=ids)
        )
        return {m.user_id: m for m in membres}

    @staticmethod
    def get_role(user_id):
        membre = AdhesionService.get_membre(user_id)
        return membre.role if membre and membre.est_active else None

    @staticmethod
    def est_membre_actif(user_id):
        membre = AdhesionService.get_membre(user_id)
        return bool(membre and membre.est_active)

    @staticmethod
    @transaction.atomic
    def get_or_create_adhesion(user_id, *, role=RoleUtilisateur.ETUDIANT,
                                statut_adhesion=StatutAdhesion.ACCEPTEE,
                                organisation=None, etablissement=None):
        """Assure que `user_id` a une adhésion dans le tenant courant --
        utilisé à l'inscription/connexion (accès immédiat par défaut,
        statut ACCEPTEE) et par bootstrap_tenant (premier administrateur).
        Ne modifie PAS une adhésion déjà existante (idempotent : rejouer
        l'inscription/connexion ne doit jamais écraser un rôle déjà
        attribué manuellement par un administrateur)."""
        membre, _created = MembreTenant.objects.get_or_create(
            user_id=user_id,
            defaults=dict(
                role=role, statut_adhesion=statut_adhesion,
                organisation=organisation, etablissement=etablissement,
            ),
        )
        return membre

    @staticmethod
    @transaction.atomic
    def traiter_demande(membre: MembreTenant, *, accepter: bool, traite_par_user_id=None, motif=''):
        from django.utils import timezone
        membre.statut_adhesion = StatutAdhesion.ACCEPTEE if accepter else StatutAdhesion.REFUSEE
        membre.traitee_le = timezone.now()
        membre.traitee_par_id = traite_par_user_id
        if not accepter:
            membre.motif_refus = motif
        membre.save(update_fields=['statut_adhesion', 'traitee_le', 'traitee_par_id', 'motif_refus'])
        return membre
