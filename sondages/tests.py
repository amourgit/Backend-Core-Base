"""
sondages/tests.py
====================
Couvre le cœur du correctif demandé :
  - la persistance de l'utilisateur votant est correcte et unique par
    (choix, utilisateur) ;
  - un sondage à choix UNIQUE ne peut jamais accumuler plusieurs votes
    actifs pour un même utilisateur (remplacement, pas addition) ;
  - un sondage à choix MULTIPLE réconcilie correctement ajouts/retraits ;
  - `visibilite_resultat = masque_jusqua_fin` est bien appliqué côté API.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient
from django_tenants.test.cases import TenantTestCase

from news.models import News, NewsType
from referentiels.models import Categorie
from .api.v1 import services
from .models import (
    Sondage, ChoixSondage, VoteSondage, TypeVoteSondage, VisibiliteResultatSondage,
)

User = get_user_model()


class SondageTenantTestCase(TenantTestCase):
    """Base commune : `sondages`/`news`/`referentiels` sont des TENANT_APPS
    (schéma par tenant, voir config/settings.py TENANT_APPS) -- leurs
    tables n'existent pas dans le schéma `public` de la base de test créée
    par défaut par le test runner Django, d'où le passage par
    `TenantTestCase` (django_tenants) qui provisionne un schéma de tenant
    dédié et y applique les migrations avant chaque classe de tests."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.sous_domaine = 'sondages-test'

    @classmethod
    def get_test_tenant_domain(cls):
        # Doit matcher le pattern sous-domaine attendu par
        # tenants.middleware.TenantMiddleware.is_valid_domain :
        # ^[a-zA-Z0-9-]+\.{MAIN_DOMAIN}$ avec MAIN_DOMAIN = 'localhost'
        # (config/settings.py) -- le domaine par défaut de TenantTestCase
        # ('tenant.test.com') ne matche pas ce pattern et se ferait
        # rejeter en 404 "Domaine ou tenant introuvable" avant même
        # d'atteindre la vue DRF.
        return 'sondages-test.localhost'


class SondageTestCaseMixin:
    def setUp(self):
        self.auteur = User.objects.create_user(username='auteur', password='x', role='organisation')
        self.alice = User.objects.create_user(username='alice', password='x')
        self.bob = User.objects.create_user(username='bob', password='x')
        self.moderateur = User.objects.create_user(username='mod', password='x', role='moderateur')

        self.categorie = Categorie.objects.create(nom='Vie académique')
        self.news = News.objects.create(
            slug='actualite-test', type=NewsType.SONDAGE, titre='Actualité test',
            description='desc', auteur=self.auteur, categorie=self.categorie,
        )

    def creer_sondage(self, type_vote=TypeVoteSondage.UNIQUE, **kwargs):
        maintenant = timezone.now()
        defaults = dict(
            news=self.news, titre='Sondage test', question='Votre préférence ?',
            date_debut=maintenant - timedelta(hours=1), date_fin=maintenant + timedelta(days=1),
            type_vote=type_vote, cree_par=self.auteur,
        )
        defaults.update(kwargs)
        sondage = Sondage.objects.create(**defaults)
        self.choix_a = ChoixSondage.objects.create(sondage=sondage, libelle='A', ordre=0)
        self.choix_b = ChoixSondage.objects.create(sondage=sondage, libelle='B', ordre=1)
        self.choix_c = ChoixSondage.objects.create(sondage=sondage, libelle='C', ordre=2)
        return sondage


class EnregistrerVoteUniqueTests(SondageTestCaseMixin, SondageTenantTestCase):
    def setUp(self):
        super().setUp()
        self.sondage = self.creer_sondage(type_vote=TypeVoteSondage.UNIQUE)

    def test_vote_persiste_l_utilisateur(self):
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        vote = VoteSondage.objects.get(sondage=self.sondage, choix=self.choix_a)
        self.assertEqual(vote.utilisateur_id, self.alice.pk)

    def test_changer_de_choix_remplace_l_ancien_vote(self):
        """Le bug corrigé : voter A puis B ne doit jamais laisser 2 votes actifs."""
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_b.pk)])

        votes_alice = VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice)
        self.assertEqual(votes_alice.count(), 1)
        self.assertEqual(votes_alice.first().choix_id, self.choix_b.pk)

    def test_revoter_le_meme_choix_est_idempotent(self):
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        self.assertEqual(
            VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice).count(), 1,
        )

    def test_retirer_son_vote(self):
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        services.retirer_vote(self.sondage, self.alice)
        self.assertFalse(VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice).exists())

    def test_deux_choix_refuses_sur_sondage_unique(self):
        with self.assertRaises(ValidationError):
            services.enregistrer_vote(
                self.sondage, self.alice, [str(self.choix_a.pk), str(self.choix_b.pk)],
            )

    def test_choix_invalide_refuse(self):
        with self.assertRaises(ValidationError):
            services.enregistrer_vote(self.sondage, self.alice, ['999999'])

    def test_votes_de_deux_utilisateurs_sont_independants(self):
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        services.enregistrer_vote(self.sondage, self.bob, [str(self.choix_a.pk)])
        self.assertEqual(VoteSondage.objects.filter(choix=self.choix_a).count(), 2)


class EnregistrerVoteMultipleTests(SondageTestCaseMixin, SondageTenantTestCase):
    def setUp(self):
        super().setUp()
        self.sondage = self.creer_sondage(type_vote=TypeVoteSondage.MULTIPLE)

    def test_selection_multiple_persiste_chaque_choix_pour_l_utilisateur(self):
        services.enregistrer_vote(
            self.sondage, self.alice, [str(self.choix_a.pk), str(self.choix_b.pk)],
        )
        votes = VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice)
        self.assertEqual(votes.count(), 2)
        self.assertTrue(all(v.utilisateur_id == self.alice.pk for v in votes))

    def test_reconciliation_ajoute_et_retire(self):
        services.enregistrer_vote(
            self.sondage, self.alice, [str(self.choix_a.pk), str(self.choix_b.pk)],
        )
        # Alice change d'avis : retire B, garde A, ajoute C.
        services.enregistrer_vote(
            self.sondage, self.alice, [str(self.choix_a.pk), str(self.choix_c.pk)],
        )
        ids_restants = set(
            VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice)
            .values_list('choix_id', flat=True)
        )
        self.assertEqual(ids_restants, {self.choix_a.pk, self.choix_c.pk})


class SondageApiTestCaseMixin(SondageTestCaseMixin):
    """Comme `SondageTestCaseMixin`, avec un client DRF pré-configuré sur
    le domaine du tenant de test -- indispensable ici : sans le header
    Host correspondant, `TenantMiddleware.is_valid_domain` rejette la
    requête en 404 avant même d'atteindre la vue (voir
    `SondageTenantTestCase.get_test_tenant_domain`).

    `TenantMiddleware.process_response` (tenants/middleware.py) repositionne
    INCONDITIONNELLEMENT la connexion sur le schéma public en fin de
    requête ("on s'assure qu'on termine sur le schéma public") -- correct
    en usage normal (une requête HTTP = une connexion qui doit repartir
    neutre), mais `TenantTestCase.setUpClass` (django_tenants) ne
    positionne le schéma tenant qu'UNE fois pour toute la classe : dès
    qu'un test de la classe fait un appel HTTP, tous les tests suivants
    de la même classe retrouvent la connexion sur le schéma public. D'où
    la resynchronisation explicite ici, avant chaque test.
    """

    def setUp(self):
        connection.set_tenant(self.tenant)
        super().setUp()
        self.client = APIClient(HTTP_HOST=self.domain.domain)


class SondageApiVoteTests(SondageApiTestCaseMixin, SondageTenantTestCase):
    def setUp(self):
        super().setUp()
        self.sondage = self.creer_sondage(type_vote=TypeVoteSondage.UNIQUE)

    def test_endpoint_vote_change_le_choix_sans_accumuler(self):
        self.client.force_authenticate(self.alice)
        url = f'/api/sondages/v1/sondages/{self.sondage.pk}/vote/'

        resp = self.client.post(url, {'choix_ids': [str(self.choix_a.pk)]}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['user_voted_choice_ids'], [self.choix_a.pk])

        resp = self.client.post(url, {'choix_ids': [str(self.choix_b.pk)]}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['user_voted_choice_ids'], [self.choix_b.pk])

        # `TenantMiddleware.process_response` repositionne la connexion
        # sur le schéma public en fin de requête HTTP (voir
        # `SondageApiTestCaseMixin`) -- on la replace sur le schéma tenant
        # avant cette vérification directe en base, après les appels API
        # ci-dessus.
        connection.set_tenant(self.tenant)
        self.assertEqual(
            VoteSondage.objects.filter(sondage=self.sondage, utilisateur=self.alice).count(), 1,
        )

    def test_endpoint_vote_refuse_anonyme(self):
        url = f'/api/sondages/v1/sondages/{self.sondage.pk}/vote/'
        resp = self.client.post(url, {'choix_ids': [str(self.choix_a.pk)]}, format='json')
        # 403 (pas 401) : DRF ne renvoie 401 que si le DERNIER authenticator
        # de DEFAULT_AUTHENTICATION_CLASSES (config/settings.py) fournit un
        # challenge WWW-Authenticate -- ici JWTAuthentication (en dernière
        # position, après Session/Basic), qui n'en fournit pas. DRF retombe
        # alors sur 403, comportement standard pour toute vue authentifiée
        # de ce projet, pas spécifique à sondages.
        self.assertEqual(resp.status_code, 403)


class SondageSerializerMetadonneesTests(SondageApiTestCaseMixin, SondageTenantTestCase):
    def setUp(self):
        super().setUp()
        self.sondage = self.creer_sondage(type_vote=TypeVoteSondage.UNIQUE)

    def test_metadonnees_communes_exposees(self):
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f'/api/sondages/v1/sondages/{self.sondage.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('created_at', resp.data)
        self.assertIn('updated_at', resp.data)
        self.assertIsNotNone(resp.data['created_at'])
        self.assertEqual(resp.data['auteur']['id'], str(self.auteur.pk))
        self.assertEqual(resp.data['auteur']['username'], 'auteur')


class ResultatsMasquesTests(SondageApiTestCaseMixin, SondageTenantTestCase):
    def setUp(self):
        super().setUp()
        self.sondage = self.creer_sondage(
            type_vote=TypeVoteSondage.UNIQUE,
            visibilite_resultat=VisibiliteResultatSondage.MASQUE_JUSQUA_FIN,
        )

    def test_resultats_masques_pour_visiteur_n_ayant_pas_vote(self):
        services.enregistrer_vote(self.sondage, self.bob, [str(self.choix_a.pk)])
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f'/api/sondages/v1/sondages/{self.sondage.pk}/')
        self.assertFalse(resp.data['resultats_visibles'])
        self.assertEqual(resp.data['total_votes'], 0)
        self.assertTrue(all(c['nombre_votes'] == 0 for c in resp.data['choix']))

    def test_resultats_visibles_apres_avoir_vote(self):
        services.enregistrer_vote(self.sondage, self.bob, [str(self.choix_a.pk)])
        services.enregistrer_vote(self.sondage, self.alice, [str(self.choix_a.pk)])
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f'/api/sondages/v1/sondages/{self.sondage.pk}/')
        self.assertTrue(resp.data['resultats_visibles'])
        self.assertEqual(resp.data['total_votes'], 2)

    def test_resultats_visibles_pour_moderateur(self):
        services.enregistrer_vote(self.sondage, self.bob, [str(self.choix_a.pk)])
        self.client.force_authenticate(self.moderateur)
        resp = self.client.get(f'/api/sondages/v1/sondages/{self.sondage.pk}/')
        self.assertTrue(resp.data['resultats_visibles'])

    def test_resultats_visibles_apres_cloture(self):
        self.sondage.date_fin = timezone.now() - timedelta(minutes=1)
        self.sondage.save(update_fields=['date_fin'])
        VoteSondage.objects.create(sondage=self.sondage, choix=self.choix_a, utilisateur=self.bob)
        self.client.force_authenticate(self.alice)
        resp = self.client.get(f'/api/sondages/v1/sondages/{self.sondage.pk}/')
        self.assertTrue(resp.data['resultats_visibles'])
