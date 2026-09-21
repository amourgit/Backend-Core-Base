"""
Tests des endpoints :
  - GET/PATCH /tenants/v1/identite/               (admin du tenant courant)
  - GET       /tenants/v1/profil-public/<sd>/     (public)

Sans base de données (SimpleTestCase + mocks ciblés) : ce qu'on vérifie
ici, c'est la LOGIQUE propre à ces endpoints -- liste blanche des champs
publics, validation, composition des permissions, écritures partielles,
nettoyage du logo -- pas la plomberie django-tenants, déjà couverte
ailleurs.
"""
import struct
import zlib
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.test import APIRequestFactory, force_authenticate

from token_manager.api.v1.permissions import IsAccessTokenTenant
from tenants.models import Tenant, TenantInformationsPrimaires, StatutVerificationIdentite
from tenants.api.v1 import views
from tenants.api.v1.permissions import EstAdministrateurDuTenant
from tenants.api.v1.serializers import (
    TenantFichePubliqueSerializer,
    TenantIdentiteSerializer,
)
from tenants.api.v1.services import TenantService

factory = APIRequestFactory()


def _png_1x1() -> bytes:
    def chunk(tag, data):
        c = struct.pack('>I', len(data)) + tag + data
        return c + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b'\x00\xff\x00\x00'
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw))
        + chunk(b'IEND', b'')
    )


# Champs qui ne doivent JAMAIS apparaître dans la fiche publique.
CHAMPS_PRIVES = {
    'numero_rccm', 'numero_nif', 'numero_agrement', 'date_creation_ou_agrement',
    'adresse_siege', 'telephone_principal', 'telephone_secondaire', 'email_contact',
    'responsable_nom_complet', 'responsable_fonction', 'responsable_telephone', 'responsable_email',
    'contact_operationnel_nom', 'contact_operationnel_fonction',
    'contact_operationnel_telephone', 'contact_operationnel_email',
    'effectif_estime', 'commentaire_verification', 'verifie_le', 'verifie_par', 'statut',
    'pourcentage_completion', 'tenant', 'id', 'cree_le', 'modifie_le',
}


class FichePubliqueSerializerTests(SimpleTestCase):
    def _fiche(self, **extra):
        return TenantInformationsPrimaires(
            raison_sociale='Acme SA', sigle='ACME', ville='Libreville', province='estuaire', pays='Gabon',
            numero_rccm='RCCM-SECRET', numero_nif='NIF-SECRET', adresse_siege='1 rue privée',
            telephone_principal='+24100000000', email_contact='contact@acme.ga',
            responsable_nom_complet='Jean Dupont', responsable_email='jean@acme.ga',
            effectif_estime=42, commentaire_verification='note interne',
            **extra,
        )

    def test_expose_uniquement_la_liste_blanche(self):
        data = TenantFichePubliqueSerializer(self._fiche()).data
        self.assertEqual(data['raison_sociale'], 'Acme SA')
        self.assertEqual(data['ville'], 'Libreville')
        self.assertFalse(CHAMPS_PRIVES & set(data.keys()), "Un champ privé fuite dans la fiche publique")

    def test_aucune_valeur_sensible_dans_la_reponse(self):
        rendu = str(TenantFichePubliqueSerializer(self._fiche()).data)
        for secret in ('RCCM-SECRET', 'NIF-SECRET', '1 rue privée', '+24100000000', 'jean@acme.ga', 'note interne'):
            self.assertNotIn(secret, rendu)

    def test_identite_verifiee_ne_revele_que_le_resultat(self):
        verifiee = TenantFichePubliqueSerializer(self._fiche(statut=StatutVerificationIdentite.VERIFIEE)).data
        a_corriger = TenantFichePubliqueSerializer(self._fiche(statut=StatutVerificationIdentite.A_CORRIGER)).data
        self.assertIs(verifiee['identite_verifiee'], True)
        self.assertIs(a_corriger['identite_verifiee'], False)
        self.assertNotIn('statut', verifiee)


class IdentiteSerializerTests(SimpleTestCase):
    def test_modification_partielle_vide_est_valide(self):
        s = TenantIdentiteSerializer(data={}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data, {})

    def test_nom_est_rogne_et_ne_peut_pas_etre_vide(self):
        ok = TenantIdentiteSerializer(data={'name': '  Acme  '}, partial=True)
        self.assertTrue(ok.is_valid(), ok.errors)
        self.assertEqual(ok.validated_data['name'], 'Acme')
        vide = TenantIdentiteSerializer(data={'name': '   '}, partial=True)
        self.assertFalse(vide.is_valid())
        self.assertIn('name', vide.errors)

    def test_nom_et_description_respectent_les_longueurs_max(self):
        s = TenantIdentiteSerializer(data={'name': 'x' * 101, 'description': 'y' * 2001}, partial=True)
        self.assertFalse(s.is_valid())
        self.assertEqual(set(s.errors), {'name', 'description'})

    def test_champs_non_autorises_sont_ignores(self):
        s = TenantIdentiteSerializer(
            data={'name': 'Acme', 'is_public': True, 'is_active': False, 'sous_domaine': 'pirate', 'schema_name': 'x'},
            partial=True,
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(set(s.validated_data), {'name'})

    def test_logo_doit_etre_une_image(self):
        faux = SimpleUploadedFile('logo.png', b'pas une image', content_type='image/png')
        s = TenantIdentiteSerializer(data={'logo': faux}, partial=True)
        self.assertFalse(s.is_valid())
        self.assertIn('logo', s.errors)

    def test_logo_trop_lourd_est_refuse(self):
        logo = SimpleUploadedFile('logo.png', _png_1x1(), content_type='image/png')
        with mock.patch('tenants.api.v1.serializers.LOGO_TAILLE_MAX_MO', 0):
            s = TenantIdentiteSerializer(data={'logo': logo}, partial=True)
            self.assertFalse(s.is_valid())
        self.assertIn('logo', s.errors)

    def test_logo_valide_est_accepte_et_null_supprime(self):
        logo = SimpleUploadedFile('logo.png', _png_1x1(), content_type='image/png')
        ok = TenantIdentiteSerializer(data={'logo': logo}, partial=True)
        self.assertTrue(ok.is_valid(), ok.errors)
        suppression = TenantIdentiteSerializer(data={'logo': None}, partial=True)
        self.assertTrue(suppression.is_valid(), suppression.errors)
        self.assertIsNone(suppression.validated_data['logo'])

    def test_la_reponse_a_la_forme_de_l_annuaire(self):
        tenant = Tenant(id=7, name='Acme', sous_domaine='acme', description='d', is_public=False)
        with mock.patch('domain.models.Domain.get_primary_domain', return_value=None):
            data = TenantIdentiteSerializer(tenant).data
        self.assertEqual(
            set(data), {'id', 'name', 'sous_domaine', 'domain', 'logo', 'description', 'is_public', 'created_at'},
        )


class ProfilPublicViewTests(SimpleTestCase):
    def _get(self, sous_domaine):
        request = factory.get(f'/api/tenants/v1/profil-public/{sous_domaine}/')
        return views.TenantProfilPublicAPIView.as_view()(request, sous_domaine=sous_domaine)

    def test_acces_public_sans_authentification(self):
        self.assertEqual(views.TenantProfilPublicAPIView.permission_classes, [AllowAny])
        self.assertEqual(views.TenantProfilPublicAPIView.authentication_classes, [])

    def test_organisation_inconnue_ou_inactive_renvoie_404(self):
        with mock.patch.object(views.Tenant, 'objects') as objects:
            objects.filter.return_value.first.return_value = None
            response = self._get('Inconnue')
        objects.filter.assert_called_once_with(is_active=True, sous_domaine='inconnue')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_profil_sans_fiche_renvoie_fiche_publique_nulle(self):
        tenant = Tenant(id=1, name='Acme', sous_domaine='acme')
        with mock.patch.object(views.Tenant, 'objects') as objects, \
             mock.patch('tenants.api.v1.serializers.TenantInformationsPrimaires.objects') as fiches, \
             mock.patch('domain.models.Domain.get_primary_domain', return_value=None):
            objects.filter.return_value.first.return_value = tenant
            fiches.filter.return_value.first.return_value = None
            response = self._get('acme')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['fiche_publique'])
        self.assertEqual(response.data['sous_domaine'], 'acme')

    def test_profil_avec_fiche_n_expose_que_les_champs_publics(self):
        tenant = Tenant(id=1, name='Acme', sous_domaine='acme')
        fiche = TenantInformationsPrimaires(raison_sociale='Acme SA', numero_nif='NIF-SECRET', ville='Libreville')
        with mock.patch.object(views.Tenant, 'objects') as objects, \
             mock.patch('tenants.api.v1.serializers.TenantInformationsPrimaires.objects') as fiches, \
             mock.patch('domain.models.Domain.get_primary_domain', return_value=None):
            objects.filter.return_value.first.return_value = tenant
            fiches.filter.return_value.first.return_value = fiche
            response = self._get('acme')
        self.assertEqual(response.data['fiche_publique']['raison_sociale'], 'Acme SA')
        self.assertNotIn('NIF-SECRET', str(response.data))


class IdentiteViewTests(SimpleTestCase):
    def test_reservee_a_l_administrateur_du_tenant_courant(self):
        self.assertEqual(
            views.TenantIdentiteAPIView.permission_classes,
            [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant],
        )

    def test_seuls_get_et_patch_sont_exposes(self):
        for methode in ('put', 'post', 'delete'):
            self.assertFalse(hasattr(views.TenantIdentiteAPIView, methode), methode)

    def _patch(self, data, tenant, fmt='json'):
        request = factory.patch('/api/tenants/v1/identite/', data, format=fmt)
        if tenant is not None:
            request.tenant = tenant
        force_authenticate(request, user=mock.Mock(is_authenticated=True, pk=1))
        # Les permissions (tokens/base) sont testées ci-dessus par composition :
        # ici on isole la logique de la vue.
        with mock.patch.object(views.TenantIdentiteAPIView, 'permission_classes', [AllowAny]):
            return views.TenantIdentiteAPIView.as_view()(request)

    def test_tenant_non_resolu_renvoie_400(self):
        self.assertEqual(self._patch({'name': 'X'}, tenant=None).status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_n_ecrit_que_les_champs_autorises_sur_le_tenant_de_la_requete(self):
        tenant = Tenant(id=3, name='Acme', sous_domaine='acme')
        with mock.patch.object(TenantService, 'mettre_a_jour_identite', return_value=tenant) as maj, \
             mock.patch('domain.models.Domain.get_primary_domain', return_value=None):
            response = self._patch({'name': 'Nouveau', 'is_public': True, 'sous_domaine': 'pirate'}, tenant)
        self.assertEqual(response.status_code, 200)
        maj.assert_called_once()
        cible, donnees = maj.call_args.args
        self.assertIs(cible, tenant)
        self.assertEqual(dict(donnees), {'name': 'Nouveau'})

    def test_donnees_invalides_renvoient_400_sans_ecriture(self):
        tenant = Tenant(id=3, name='Acme', sous_domaine='acme')
        with mock.patch.object(TenantService, 'mettre_a_jour_identite') as maj:
            response = self._patch({'name': '  '}, tenant)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        maj.assert_not_called()


class ClassificationDesRoutesTests(SimpleTestCase):
    """Le middleware refuse (404 « Type de route non géré ») toute route non
    classée dans config/config.py -- et classer à tort une route privée en
    TENANT_PUBLIC la rendrait accessible sans token."""

    def setUp(self):
        from tenants.middleware import TenantMiddleware
        self.middleware = TenantMiddleware(lambda request: None)

    def test_identite_exige_une_authentification(self):
        self.assertEqual(self.middleware.get_route_type('/api/tenants/v1/identite/'), 'AUTHENTICATED')

    def test_profil_public_reste_public(self):
        self.assertEqual(self.middleware.get_route_type('/api/tenants/v1/profil-public/acme/'), 'TENANT_PUBLIC')


class MettreAJourIdentiteServiceTests(SimpleTestCase):
    def setUp(self):
        self.storage = mock.MagicMock()
        patcher = mock.patch.object(Tenant._meta.get_field('logo'), 'storage', self.storage)
        patcher.start()
        self.addCleanup(patcher.stop)
        for cible in ('tenants.api.v1.services.transaction',):
            p = mock.patch(cible)
            p.start()
            self.addCleanup(p.stop)

    def _tenant(self, logo='tenant_logos/ancien.png'):
        return Tenant(id=1, name='Acme', sous_domaine='acme', description='avant', logo=logo)

    def _appliquer(self, tenant, donnees):
        with mock.patch.object(Tenant, 'objects') as objects, mock.patch.object(Tenant, 'save') as save:
            objects.select_for_update.return_value.get.return_value = tenant
            resultat = TenantService.mettre_a_jour_identite(tenant, donnees)
        return resultat, save

    def test_sans_champ_a_modifier_n_ecrit_rien(self):
        tenant = self._tenant()
        with mock.patch.object(Tenant, 'objects') as objects:
            self.assertIs(TenantService.mettre_a_jour_identite(tenant, {}), tenant)
        objects.select_for_update.assert_not_called()

    def test_ecriture_partielle_limitee_aux_champs_fournis(self):
        tenant = self._tenant()
        _, save = self._appliquer(tenant, {'name': 'Nouveau'})
        save.assert_called_once_with(update_fields=['name', 'updated_at'])
        self.assertEqual(tenant.name, 'Nouveau')
        self.assertEqual(tenant.description, 'avant')
        self.storage.delete.assert_not_called()

    def test_logo_supprime_efface_l_ancien_fichier(self):
        tenant = self._tenant()
        self._appliquer(tenant, {'logo': None})
        self.storage.delete.assert_called_once_with('tenant_logos/ancien.png')

    def test_logo_remplace_efface_l_ancien_fichier(self):
        tenant = self._tenant()
        self._appliquer(tenant, {'logo': 'tenant_logos/nouveau.png'})
        self.storage.delete.assert_called_once_with('tenant_logos/ancien.png')

    def test_echec_du_nettoyage_ne_fait_pas_echouer_la_mise_a_jour(self):
        tenant = self._tenant()
        self.storage.delete.side_effect = OSError('stockage indisponible')
        resultat, save = self._appliquer(tenant, {'logo': None})
        self.assertIs(resultat, tenant)
        save.assert_called_once()
