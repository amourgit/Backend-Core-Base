"""
common/storage.py
==================

Sélection du backend de stockage pour les `FileField` qui NE sont PAS des
images pures (fichiers polymorphes pouvant être une vidéo, un audio ou un
document : `NewsMedia.fichier`, `DocumentJoint.fichier`,
`MediaJointCommentaire.fichier`, `Commentaire.audio_fichier`).

Pourquoi ce fichier existe
--------------------------
Quand Cloudinary est actif (voir `CLOUDINARY_URL` dans `config/settings.py`),
le storage "default" (`MediaCloudinaryStorage`) envoie tout à Cloudinary en
`resource_type="image"`. C'est correct pour un `ImageField`, mais Cloudinary
REJETTE l'upload d'un PDF, d'un fichier audio ou d'une vidéo envoyé avec
`resource_type="image"`. Ces champs ont donc besoin d'un storage dédié
(`RawMediaCloudinaryStorage`, `resource_type="raw"`, qui accepte n'importe
quel type de fichier, sans transformation Cloudinary appliquée dessus).

Quand Cloudinary n'est PAS actif (S3/compatible via `AWS_STORAGE_BUCKET_NAME`,
ou `FileSystemStorage` en dev local), cette distinction n'existe pas : ces
deux backends stockent n'importe quel type de fichier de la même façon que
le storage "default" -- donc pas besoin d'un storage différent.

Pourquoi une fonction et non une instance statique
---------------------------------------------------
Django accepte un `callable` comme argument `storage=` d'un `FileField`
(voir `FileField.__init__`, ligne "if callable(self.storage)"). Ce callable
n'est appelé qu'une seule fois, au chargement du modèle -- donc APRES que
les settings (et `CLOUDINARY_URL`) soient déjà chargés. C'est ce qui permet
à ce module de rester agnostique de l'environnement (local/Render, avec ou
sans Cloudinary) sans aucune condition à dupliquer dans chaque `models.py`.
Autre avantage : Django sérialise dans les migrations une RÉFÉRENCE vers
cette fonction (pas une instance de storage résolue) -- donc changer de
backend de stockage plus tard (ex: quitter Cloudinary pour S3) ne nécessite
PAS de nouvelle migration, seulement de changer la variable d'environnement.
"""
from django.conf import settings


def get_raw_media_storage():
    """Storage à utiliser pour un FileField non-image (vidéo/audio/document)."""
    if getattr(settings, 'CLOUDINARY_URL', None):
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    from django.core.files.storage import default_storage
    return default_storage
