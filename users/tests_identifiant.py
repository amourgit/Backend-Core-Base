"""
Tests unitaires PURS (aucun accès base de données) pour les helpers de
détection/normalisation d'identifiant de connexion (email OU téléphone)
introduits dans users/api/v1/services.py.

Les flux complets login/register (avec création réelle d'utilisateur,
recherche en base, émission de session) nécessitent un tenant + schéma
PostgreSQL constitués (django-tenants) -- non exécutables sans une
instance Postgres locale. Ce module se limite donc volontairement aux
fonctions pures, exécutables avec `python manage.py test users.tests_identifiant`
sans aucune dépendance externe.
"""
from django.test import SimpleTestCase
from users.api.v1.services import (
    is_email,
    is_telephone_valide,
    normaliser_telephone,
    normaliser_identifiant,
)


class DetectionIdentifiantTests(SimpleTestCase):
    def test_email_valide_est_detecte(self):
        self.assertTrue(is_email('samuel@civitas.ga'))

    def test_telephone_nest_pas_un_email(self):
        self.assertFalse(is_email('074123456'))

    def test_chaine_arbitraire_nest_pas_un_email(self):
        self.assertFalse(is_email('pas-un-email'))

    def test_telephone_local_valide(self):
        self.assertTrue(is_telephone_valide('074123456'))

    def test_telephone_international_valide(self):
        self.assertTrue(is_telephone_valide('+24174123456'))

    def test_chaine_arbitraire_nest_pas_un_telephone(self):
        self.assertFalse(is_telephone_valide('abc'))

    def test_telephone_trop_court_est_invalide(self):
        self.assertFalse(is_telephone_valide('12345'))


class NormalisationIdentifiantTests(SimpleTestCase):
    def test_telephone_avec_espaces_et_tirets_normalise_pareil(self):
        self.assertEqual(normaliser_telephone('074 12 34 56'), '074123456')
        self.assertEqual(normaliser_telephone('074-12-34-56'), '074123456')

    def test_telephone_international_garde_le_plus(self):
        self.assertEqual(normaliser_telephone('+241 74-12-34-56'), '+24174123456')

    def test_email_normalise_en_minuscules_et_trim(self):
        self.assertEqual(normaliser_identifiant('  Samuel@Civitas.GA  '), 'samuel@civitas.ga')

    def test_deux_saisies_telephone_differentes_convergent(self):
        """Ce test protège directement le scénario produit demandé : deux
        saisies visuellement différentes du MÊME numéro doivent être
        reconnues comme le même identifiant de connexion, faute de quoi
        un utilisateur pourrait se voir proposer de créer un second
        compte pour un numéro qu'il possède déjà (juste tapé différemment
        au login vs à l'inscription)."""
        self.assertEqual(
            normaliser_identifiant('074 12 34 56'),
            normaliser_identifiant('074-12-34-56'),
        )


class NormalisationChaineVideAvantSaveTests(SimpleTestCase):
    """
    User.save() DOIT convertir '' -> None pour email/phone_number AVANT
    d'atteindre la base -- voir users/models.py:User.save(). Sans ce
    garde-fou, DEUX comptes créés sans téléphone (ex: via l'admin Django,
    `createsuperuser`, ou UserCreateSerializer qui ne fournit même pas ce
    champ) entreraient en collision sur la contrainte unique dès le
    second, PostgreSQL ne traitant jamais deux '' comme distincts (à la
    différence de deux NULL).

    Testé ici SANS toucher la base : on intercepte l'appel à
    Model.save() (la classe mère, juste avant l'écriture réelle) pour
    vérifier l'état de l'instance à ce moment précis.
    """
    def test_email_vide_devient_none_avant_le_save_reel(self):
        from unittest.mock import patch
        from django.db.models import Model
        from users.models import User

        user = User(username='sans_email', email='', phone_number='074123456')
        with patch.object(Model, 'save', autospec=True) as mock_save:
            user.save()
        self.assertIsNone(user.email)
        self.assertEqual(user.phone_number, '074123456')
        mock_save.assert_called_once()

    def test_telephone_vide_devient_none_avant_le_save_reel(self):
        from unittest.mock import patch
        from django.db.models import Model
        from users.models import User

        user = User(username='sans_telephone', email='sans.telephone@civitas.ga', phone_number='')
        with patch.object(Model, 'save', autospec=True) as mock_save:
            user.save()
        self.assertIsNone(user.phone_number)
        self.assertEqual(user.email, 'sans.telephone@civitas.ga')
        mock_save.assert_called_once()

    def test_valeurs_deja_none_restent_inchangees(self):
        from unittest.mock import patch
        from django.db.models import Model
        from users.models import User

        user = User(username='deja_none', email=None, phone_number=None)
        with patch.object(Model, 'save', autospec=True):
            user.save()
        self.assertIsNone(user.email)
        self.assertIsNone(user.phone_number)
