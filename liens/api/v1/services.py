"""
liens/api/v1/services.py
===========================
"""

from django.utils import timezone

from ... import models


def enregistrer_acces(lien: models.LienPublication, type_acces: str, adresse_ip: str = None) -> None:
    models.LienAcces.objects.create(lien=lien, type_acces=type_acces, adresse_ip=adresse_ip)
    if lien.usage_unique and not lien.deja_utilise:
        lien.deja_utilise = True
        lien.save(update_fields=['deja_utilise'])


def lien_est_valide(lien: models.LienPublication) -> bool:
    if lien.expiration and lien.expiration < timezone.now():
        return False
    if lien.usage_unique and lien.deja_utilise:
        return False
    return True
