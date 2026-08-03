from django.utils import timezone
from rest_framework import status
from config.fonction import formatReponse
from .services import TokenService
from token_manager.models import TokenSettings

def check_and_revoke_token_if_expired(data, lifeTimeRefresh=None):
    """
    Vérifie si le token existe et s'il a expiré, le révoque si besoin.
    :param access_token: str
    :param refresh_token: str
    :param lifetime_seconds: int (durée de vie du token en secondes)
    :return: dict (état du token et infos)
    """

    stat = False
    # 1. Vérifier que le token existe dans notre base de données
    token_obj, formatReponse = TokenService.get_token_by_choice_data(data)
    if token_obj is None:
        formatReponse['message'] = "Le Token n'est pas valide ou n'existe pas"
        return formatReponse, stat
    
    formatReponse['type'] = 'info'
    formatReponse['titre'] = 'Revocation'
    formatReponse['status'] = 200

    # if not lifeTimeRefresh == None:
    #     formatReponse['titre'] = 'Verification Refresh Token'
    #     now = timezone.now()
    #     elapsed = (now - lifeTimeRefresh).total_seconds()
    #     if elapsed >= lifeTimeRefresh:
    #         formatReponse['niveau'] = 100
    #         formatReponse['message'] = "Refresh Token deja expiré"
    #         formatReponse['date_aujourdhui'] = now
    #         formatReponse['date_creation'] = token_obj.created_at
    #         stat = False
    #         return formatReponse, stat


    now = timezone.now()
    elapsed = (now - token_obj.expires_at).total_seconds()
    if now >= token_obj.expires_at:
        formatReponse['message'] = "Token deja expiré et révoqué"
        if not token_obj.is_revoked:
            formatReponse['type'] = 'succes'
            formatReponse['message'] = "Token expiré et révoqué avec succes"
            token_obj.is_revoked = True
            token_obj.revoked_at = now
            token_obj.save(update_fields=['is_revoked', 'revoked_at'])
        formatReponse['niveau'] = 100
        formatReponse['date_revocation'] = token_obj.revoked_at
        formatReponse['elapsed_seconds'] = elapsed
        return formatReponse, stat
    
    else:
        formatReponse['type'] = 'info'
        formatReponse['niveau'] = 100
        formatReponse['message'] = "Le Token est encore valide"
        # Bug corrigé : token_obj.expires_at est un datetime, pas un
        # timedelta -- .total_seconds() doit être appelé sur la DIFFÉRENCE
        # entre l'expiration et maintenant, pas sur le datetime lui-même
        # (l'ancien code plantait systématiquement en AttributeError dès
        # qu'un token encore valide était vérifié).
        formatReponse['remaining_seconds'] = (token_obj.expires_at - now).total_seconds()
        return formatReponse, stat
    


def check_token_settings():
    global formatReponse
    stat = False
    settings_token_actif = TokenSettings.get_active_settings()
    if not settings_token_actif:
        formatReponse['type'] = 'error systeme'
        formatReponse['titre'] = 'Service systeme'
        formatReponse['niveau'] = 100
        formatReponse['code'] = 5000
        formatReponse['message'] = "Il y a une erreur imprevue. veuillez contacter votre administrateur"
        formatReponse['status'] = int(status.HTTP_400_BAD_REQUEST)
    else:
        stat = True
    return formatReponse, stat, settings_token_actif


def check_kick_token_settings():
    return TokenSettings.get_active_settings()