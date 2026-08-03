from django.test import TestCase, Client, RequestFactory
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Tenant, TokenSettings, TokenManager
from domain.models import Domain
from .services import TokenService
from django.utils import timezone
import uuid
from datetime import timedelta

User = get_user_model()

class TokenSettingsTests(TestCase):
    def setUp(self):
        self.token_settings = TokenSettings.objects.create(
            name="Test Settings",
            access_token_lifetime=5,
            refresh_token_lifetime=10,
            max_tokens_per_user=5,
            rotate_refresh_tokens=True,
            blacklist_after_rotation=True,
            cookie_secure=True,
            cookie_samesite='Lax',
            cookie_domain='example.com',
            enable_blacklist=True,
            blacklist_cleanup_after=60,
            require_https=True,
            validate_ip=True,
            validate_user_agent=True,
            is_active=True
        )

    def test_token_settings_creation(self):
        self.assertEqual(self.token_settings.name, "Test Settings")
        self.assertEqual(self.token_settings.access_token_lifetime, 5)
        self.assertEqual(self.token_settings.refresh_token_lifetime, 10)
        self.assertTrue(self.token_settings.is_active)

    def test_to_jwt_settings(self):
        jwt_settings = self.token_settings.to_jwt_settings()
        self.assertEqual(jwt_settings['ACCESS_TOKEN_LIFETIME'].total_seconds(), 5 * 60)
        self.assertEqual(jwt_settings['REFRESH_TOKEN_LIFETIME'].total_seconds(), 10 * 60)
        self.assertTrue(jwt_settings['ROTATE_REFRESH_TOKENS'])
        self.assertTrue(jwt_settings['BLACKLIST_AFTER_ROTATION'])

class TokenManagerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token = TokenManager.objects.create(
            user=self.user,
            jti=uuid.uuid4(),
            access_token='test_access_token',
            refresh_token='test_refresh_token',
            ip_address='127.0.0.1',
            user_agent='test-agent',
            expires_at=timezone.now() + timezone.timedelta(minutes=5)
        )

    def test_token_creation(self):
        self.assertEqual(self.token.user, self.user)
        self.assertFalse(self.token.is_revoked)
        self.assertIsNone(self.token.revoked_at)

    def test_token_validation(self):
        self.assertTrue(self.token.is_valid())
        self.token.revoke()
        self.assertFalse(self.token.is_valid())

    def test_token_update_last_used(self):
        old_last_used = self.token.last_used_at
        self.token.update_last_used()
        self.assertGreater(self.token.last_used_at, old_last_used)

class TokenServiceTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token_settings = TokenSettings.objects.create(
            name="Test Settings",
            access_token_lifetime=5,
            refresh_token_lifetime=10,
            is_active=True
        )
        self.client = Client()

    def test_generate_tokens(self):
        tokens = TokenService.generate_tokens(self.user)
        self.assertIn('access', tokens)
        self.assertIn('refresh', tokens)
        self.assertIn('jti', tokens)

    def test_validate_token(self):
        tokens = TokenService.generate_tokens(self.user)
        self.assertTrue(TokenService.validate_token(tokens['access']))

    def test_revoke_token(self):
        tokens = TokenService.generate_tokens(self.user)
        self.assertTrue(TokenService.revoke_token(tokens['access']))
        self.assertFalse(TokenService.validate_token(tokens['access']))

    def test_revoke_all_user_tokens(self):
        # Générer plusieurs tokens
        TokenService.generate_tokens(self.user)
        TokenService.generate_tokens(self.user)
        
        # Révoquer tous les tokens
        TokenService.revoke_all_user_tokens(self.user)
        
        # Vérifier que tous les tokens sont révoqués
        tokens = TokenManager.objects.filter(user=self.user)
        self.assertTrue(all(token.is_revoked for token in tokens))

class AuthenticationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.token_settings = TokenSettings.objects.create(
            name="Test Settings",
            access_token_lifetime=5,
            refresh_token_lifetime=10,
            is_active=True
        )
        self.client = Client()

    def test_token_obtain(self):
        url = reverse('token_obtain_pair')
        data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_token_refresh(self):
        # Obtenir un token
        url = reverse('token_obtain_pair')
        data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        response = self.client.post(url, data)
        refresh_token = response.data['refresh']

        # Rafraîchir le token
        url = reverse('token_refresh')
        data = {'refresh': refresh_token}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_logout(self):
        # Obtenir un token
        url = reverse('token_obtain_pair')
        data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        response = self.client.post(url, data)
        access_token = response.data['access']

        # Se déconnecter
        url = reverse('logout')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Vérifier que le token est révoqué
        self.assertFalse(TokenService.validate_token(access_token))

class MultiTenantTokenTests(APITestCase):
    def setUp(self):
        # Créer deux tenants
        self.tenant1 = Tenant.objects.create(
            name="Tenant 1",
            sous_domaine="tenant1",
            schema_name="tenant1"
        )
        self.tenant2 = Tenant.objects.create(
            name="Tenant 2",
            sous_domaine="tenant2",
            schema_name="tenant2"
        )

        # Créer des domaines pour chaque tenant
        self.domain1 = Domain.objects.create(
            tenant=self.tenant1,
            domain="tenant1.example.com",
            is_primary=True
        )
        self.domain2 = Domain.objects.create(
            tenant=self.tenant2,
            domain="tenant2.example.com",
            is_primary=True
        )

        # Créer des utilisateurs pour chaque tenant
        self.user1 = User.objects.create_user(
            username='user1',
            password='pass123',
            email='user1@tenant1.com'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            password='pass123',
            email='user2@tenant2.com'
        )

        # Créer des configurations de token pour chaque tenant
        self.token_settings1 = TokenSettings.objects.create(
            tenant=self.tenant1,
            name="Settings Tenant 1",
            access_token_lifetime=5,
            refresh_token_lifetime=10,
            is_active=True
        )
        self.token_settings2 = TokenSettings.objects.create(
            tenant=self.tenant2,
            name="Settings Tenant 2",
            access_token_lifetime=10,
            refresh_token_lifetime=20,
            is_active=True
        )

        # Créer une requête mock pour chaque tenant
        self.request1 = type('Request', (), {'tenant': self.tenant1, 'META': {}})()
        self.request2 = type('Request', (), {'tenant': self.tenant2, 'META': {}})()

    def test_token_generation_per_tenant(self):
        """Teste la génération de tokens spécifiques à chaque tenant"""
        # Générer des tokens pour chaque utilisateur dans leur tenant respectif
        tokens1 = TokenService.generate_tokens(self.user1, self.request1)
        tokens2 = TokenService.generate_tokens(self.user2, self.request2)

        # Vérifier que les tokens sont bien associés aux bons tenants
        token1 = TokenManager.objects.get(jti=tokens1['jti'])
        token2 = TokenManager.objects.get(jti=tokens2['jti'])

        self.assertEqual(token1.tenant, self.tenant1)
        self.assertEqual(token2.tenant, self.tenant2)

    def test_token_validation_per_tenant(self):
        """Teste la validation de tokens dans le bon tenant"""
        # Générer un token pour tenant1
        tokens = TokenService.generate_tokens(self.user1, self.request1)
        
        # Vérifier que le token est valide dans tenant1
        self.assertTrue(TokenService.validate_token(tokens['access'], self.request1))
        
        # Vérifier que le token n'est pas valide dans tenant2
        self.assertFalse(TokenService.validate_token(tokens['access'], self.request2))

    def test_token_revocation_per_tenant(self):
        """Teste la révocation de tokens par tenant"""
        # Générer des tokens pour chaque utilisateur
        tokens1 = TokenService.generate_tokens(self.user1, self.request1)
        tokens2 = TokenService.generate_tokens(self.user2, self.request2)

        # Révoquer les tokens de tenant1
        TokenService.revoke_all_user_tokens(self.user1, self.tenant1)

        # Vérifier que seul le token de tenant1 est révoqué
        token1 = TokenManager.objects.get(jti=tokens1['jti'])
        token2 = TokenManager.objects.get(jti=tokens2['jti'])

        self.assertTrue(token1.is_revoked)
        self.assertFalse(token2.is_revoked)

    def test_token_cleanup_per_tenant(self):
        """Teste le nettoyage des tokens par tenant"""
        # Générer des tokens pour chaque utilisateur
        TokenService.generate_tokens(self.user1, self.request1)
        TokenService.generate_tokens(self.user2, self.request2)

        # Nettoyer les tokens de tenant1
        TokenService.cleanup_expired_tokens(self.tenant1)

        # Vérifier que seuls les tokens de tenant1 sont nettoyés
        self.assertEqual(TokenManager.objects.filter(tenant=self.tenant1).count(), 0)
        self.assertEqual(TokenManager.objects.filter(tenant=self.tenant2).count(), 1)

    def test_token_settings_per_tenant(self):
        """Teste que les paramètres de token sont bien spécifiques à chaque tenant"""
        # Vérifier que les paramètres sont différents
        self.assertNotEqual(
            self.token_settings1.access_token_lifetime,
            self.token_settings2.access_token_lifetime
        )

        # Vérifier que les paramètres sont bien appliqués
        jwt_settings1 = self.token_settings1.to_jwt_settings()
        jwt_settings2 = self.token_settings2.to_jwt_settings()

        self.assertEqual(jwt_settings1['ACCESS_TOKEN_LIFETIME'].total_seconds(), 5 * 60)
        self.assertEqual(jwt_settings2['ACCESS_TOKEN_LIFETIME'].total_seconds(), 10 * 60)

class TokenServiceMultiTenantTests(APITestCase):
    def setUp(self):
        # Créer deux tenants
        self.tenant1 = Tenant.objects.create(
            name='Tenant 1',
            schema_name='tenant1',
            paid_until='2024-12-31',
            on_trial=False
        )
        self.tenant2 = Tenant.objects.create(
            name='Tenant 2',
            schema_name='tenant2',
            paid_until='2024-12-31',
            on_trial=False
        )

        # Créer des domaines pour chaque tenant
        self.domain1 = Domain.objects.create(
            domain='tenant1.localhost',
            tenant=self.tenant1,
            is_primary=True
        )
        self.domain2 = Domain.objects.create(
            domain='tenant2.localhost',
            tenant=self.tenant2,
            is_primary=True
        )

        # Créer des configurations de token pour chaque tenant
        self.token_settings1 = TokenSettings.objects.create(
            tenant=self.tenant1,
            access_token_lifetime=30,
            refresh_token_lifetime=1440,
            enable_blacklist=True,
            blacklist_cleanup_after=60,
            validate_ip=True,
            validate_user_agent=True,
            is_active=True
        )
        self.token_settings2 = TokenSettings.objects.create(
            tenant=self.tenant2,
            access_token_lifetime=60,
            refresh_token_lifetime=2880,
            enable_blacklist=False,
            blacklist_cleanup_after=120,
            validate_ip=False,
            validate_user_agent=False,
            is_active=True
        )

        # Créer des utilisateurs pour chaque tenant
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@tenant1.com',
            password='password123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@tenant2.com',
            password='password123'
        )

        # Créer des tokens pour chaque utilisateur
        self.token1 = TokenManager.objects.create(
            user=self.user1,
            tenant=self.tenant1,
            jti=uuid.uuid4(),
            access_token='token1',
            refresh_token='refresh1',
            ip_address='127.0.0.1',
            user_agent='test-agent',
            expires_at=timezone.now() + timedelta(minutes=30)
        )
        self.token2 = TokenManager.objects.create(
            user=self.user2,
            tenant=self.tenant2,
            jti=uuid.uuid4(),
            access_token='token2',
            refresh_token='refresh2',
            ip_address='127.0.0.1',
            user_agent='test-agent',
            expires_at=timezone.now() + timedelta(minutes=60)
        )

        self.factory = RequestFactory()

    def test_token_generation_per_tenant(self):
        """Teste la génération de tokens spécifiques à chaque tenant"""
        # Créer une requête pour tenant1
        request1 = self.factory.get('/')
        request1.tenant = self.tenant1
        request1.META['REMOTE_ADDR'] = '127.0.0.1'
        request1.META['HTTP_USER_AGENT'] = 'test-agent'

        # Créer une requête pour tenant2
        request2 = self.factory.get('/')
        request2.tenant = self.tenant2
        request2.META['REMOTE_ADDR'] = '127.0.0.1'
        request2.META['HTTP_USER_AGENT'] = 'test-agent'

        # Générer des tokens pour chaque tenant
        tokens1 = TokenService.generate_tokens(self.user1, request1)
        tokens2 = TokenService.generate_tokens(self.user2, request2)

        # Vérifier que les tokens sont créés avec les bons paramètres
        token1 = TokenManager.objects.get(jti=tokens1['jti'])
        token2 = TokenManager.objects.get(jti=tokens2['jti'])

        self.assertEqual(token1.tenant, self.tenant1)
        self.assertEqual(token2.tenant, self.tenant2)
        self.assertEqual(token1.user, self.user1)
        self.assertEqual(token2.user, self.user2)

    def test_token_validation_per_tenant(self):
        """Teste la validation de tokens spécifiques à chaque tenant"""
        # Créer des requêtes pour chaque tenant
        request1 = self.factory.get('/')
        request1.tenant = self.tenant1
        request1.META['REMOTE_ADDR'] = '127.0.0.1'
        request1.META['HTTP_USER_AGENT'] = 'test-agent'

        request2 = self.factory.get('/')
        request2.tenant = self.tenant2
        request2.META['REMOTE_ADDR'] = '127.0.0.1'
        request2.META['HTTP_USER_AGENT'] = 'test-agent'

        # Vérifier que les tokens sont valides pour leur tenant respectif
        self.assertTrue(TokenService.validate_token(self.token1.access_token, request1))
        self.assertTrue(TokenService.validate_token(self.token2.access_token, request2))

        # Vérifier que les tokens ne sont pas valides pour l'autre tenant
        self.assertFalse(TokenService.validate_token(self.token1.access_token, request2))
        self.assertFalse(TokenService.validate_token(self.token2.access_token, request1))

    def test_token_revocation_per_tenant(self):
        """Teste la révocation de tokens spécifiques à chaque tenant"""
        # Révoquer les tokens
        TokenService.revoke_token(self.token1.access_token)
        TokenService.revoke_token(self.token2.access_token)

        # Vérifier que les tokens sont révoqués
        self.token1.refresh_from_db()
        self.token2.refresh_from_db()
        self.assertTrue(self.token1.is_revoked)
        self.assertTrue(self.token2.is_revoked)

        # Vérifier que la révocation est spécifique au tenant
        self.assertEqual(self.token1.tenant, self.tenant1)
        self.assertEqual(self.token2.tenant, self.tenant2)

    def test_cleanup_tokens_per_tenant(self):
        """Teste le nettoyage des tokens expirés par tenant"""
        # Créer des tokens expirés pour chaque tenant
        expired_token1 = TokenManager.objects.create(
            user=self.user1,
            tenant=self.tenant1,
            jti=uuid.uuid4(),
            access_token='expired1',
            refresh_token='expired_refresh1',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        expired_token2 = TokenManager.objects.create(
            user=self.user2,
            tenant=self.tenant2,
            jti=uuid.uuid4(),
            access_token='expired2',
            refresh_token='expired_refresh2',
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        # Nettoyer les tokens expirés pour tenant1
        TokenService.cleanup_expired_tokens(self.tenant1)
        self.assertFalse(TokenManager.objects.filter(id=expired_token1.id).exists())
        self.assertTrue(TokenManager.objects.filter(id=expired_token2.id).exists())

        # Nettoyer les tokens expirés pour tenant2
        TokenService.cleanup_expired_tokens(self.tenant2)
        self.assertFalse(TokenManager.objects.filter(id=expired_token2.id).exists())

    def test_token_settings_per_tenant(self):
        """Teste que les paramètres de token sont respectés par tenant"""
        # Vérifier que les paramètres sont différents entre les tenants
        self.assertNotEqual(
            self.token_settings1.access_token_lifetime,
            self.token_settings2.access_token_lifetime
        )
        self.assertNotEqual(
            self.token_settings1.refresh_token_lifetime,
            self.token_settings2.refresh_token_lifetime
        )
        self.assertNotEqual(
            self.token_settings1.validate_ip,
            self.token_settings2.validate_ip
        )
        self.assertNotEqual(
            self.token_settings1.validate_user_agent,
            self.token_settings2.validate_user_agent
        )

        # Vérifier que les tokens sont créés avec les bons paramètres
        request1 = self.factory.get('/')
        request1.tenant = self.tenant1
        request1.META['REMOTE_ADDR'] = '127.0.0.1'
        request1.META['HTTP_USER_AGENT'] = 'test-agent'

        tokens1 = TokenService.generate_tokens(self.user1, request1)
        token1 = TokenManager.objects.get(jti=tokens1['jti'])

        # Vérifier que le token expire selon les paramètres du tenant
        expected_expiry = timezone.now() + timedelta(minutes=self.token_settings1.access_token_lifetime)
        self.assertAlmostEqual(
            token1.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=1  # 1 seconde de marge
        )
