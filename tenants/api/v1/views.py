import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from tenants.models import Tenant
from .serializers import TenantSerializer, TenantCreateSerializer, TenantPublicSerializer
from rest_framework.permissions import AllowAny
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .services import TenantService
from token_manager.api.v1.utils import check_token_settings
from domain.api.v1.services import DomainService
from django.utils.text import slugify
from django.conf import settings
from django.utils import timezone


class TenantCreateAPIView(APIView):
    """
    GET  : annuaire public des tenants actifs -- civitas-news l'affiche
           sur sa page d'accueil, section "Organisations" (chaque tenant
           EST une organisation, voir OrganisationsSection.tsx côté
           frontend ; referentiels.Organisation reste un tout autre
           concept -- un contenu publiable À L'INTÉRIEUR d'un tenant).
    POST : création self-service d'un nouveau tenant + de son premier
           administrateur -- architecture tenant-autonome restaurée,
           voir Tenant.create_with_domain (tenants/models.py) : chaque
           tenant a ses PROPRES utilisateurs, isolés, l'admin créé ici
           n'existe que dans le schéma de CE tenant.
    """
    permission_classes = [AllowAny]  # accessible publiquement, y compris sans aucun tenant résolu
    authentication_classes = []

    def get(self, request):
        # Tenant/Domain vivent en schéma public (SHARED_APPS) : accessible
        # tel quel, sans schema_context explicite, quel que soit le
        # schéma actif sur la connexion (voir résolution du tenant par
        # TenantMiddleware -- toujours public+courant sur le search_path).
        tenants = Tenant.objects.filter(is_active=True).order_by('name')
        serializer = TenantPublicSerializer(tenants, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description="Créer un nouveau tenant avec son premier administrateur (compte propre à ce tenant).",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['name', 'sous_domaine', 'identifiant', 'password'],
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description="Nom du tenant"),
                'sous_domaine': openapi.Schema(type=openapi.TYPE_STRING, description="Sous-domaine pour le tenant (ex: 'mon-tenant' pour mon-tenant.MAIN_DOMAIN)"),
                'description': openapi.Schema(type=openapi.TYPE_STRING, description="Description publique (optionnelle)"),
                'identifiant': openapi.Schema(type=openapi.TYPE_STRING, description="Email OU numéro de téléphone de l'administrateur"),
                'password': openapi.Schema(type=openapi.TYPE_STRING, description="Mot de passe de l'administrateur"),
            },
        ),
        responses={
            201: openapi.Response(
                description="Tenant créé avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'tenant': openapi.Schema(type=openapi.TYPE_OBJECT),
                        'domaine': openapi.Schema(type=openapi.TYPE_STRING),
                        'admin': openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                            'identifiant': openapi.Schema(type=openapi.TYPE_STRING),
                        }),
                    }
                )
            ),
            400: "Données invalides",
            500: "Erreur interne du serveur"
        }
    )
    def post(self, request):
        serializer = TenantCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Forcer l'utilisation du schéma public pour la création : la
        # requête a pu résoudre un tenant existant via X-Tenant-Domain
        # (ex: le domaine du frontend qui héberge ce formulaire), mais
        # Tenant/Domain ne vivent QUE dans le schéma public.
        with schema_context('public'):
            try:
                tenant, domain, admin_credentials = Tenant.create_with_domain(
                    name=serializer.validated_data['name'],
                    sous_domaine=serializer.validated_data['sous_domaine'],
                    description=serializer.validated_data.get('description', ''),
                    identifiant=serializer.validated_data['identifiant'],
                    password=serializer.validated_data['password'],
                )
            except ValidationError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({"detail": "Erreur interne."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({
                "tenant": TenantPublicSerializer(tenant).data,
                "domaine": domain.domain,
                # Mot de passe volontairement absent : celui du formulaire
                # est déjà connu du frontend qui vient de l'envoyer --
                # jamais renvoyé en clair par l'API.
                "admin": {"identifiant": admin_credentials['identifiant']},
            }, status=status.HTTP_201_CREATED)


class TenantPublicsAPIView(APIView):
    """
    GET /tenants/v1/publics/ -- liste des tenants `is_public=True` actifs,
    destinée au frontend pour la réforme multi-tenant des requêtes GET :
    au démarrage (puis à intervalle), le frontend appelle cet endpoint et
    garde le résultat en store + localStorage ; pour CHAQUE requête GET
    suivante, il ajoute le champ `domain` de chacun de ces tenants (voir
    TenantPublicSerializer.get_domain) à l'en-tête X-Tenant-Domain, en
    plus du domaine du tenant courant de l'utilisateur -- le backend
    (tenants.middleware.TenantMiddleware._fan_out_get) boucle alors sur
    la liste complète et renvoie les données de chaque tenant séparément.

    Volontairement un endpoint DÉDIÉ plutôt qu'un filtre `?is_public=true`
    sur GET /tenants/v1/ : cette dernière route reste l'annuaire complet
    utilisé par la page d'accueil (OrganisationsSection.tsx), un usage
    différent qui ne doit pas changer de forme selon un query param.

    Accessible sans authentification ni tenant résolu (AllowAny, schéma
    public) -- exactement comme TenantCreateAPIView.get, dont elle
    partage le même besoin d'être appelable AVANT que le frontend ne
    sache quoi que ce soit sur l'utilisateur ou son tenant.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        tenants = Tenant.objects.filter(is_active=True, is_public=True).order_by('name')
        serializer = TenantPublicSerializer(tenants, many=True)
        return Response(serializer.data)


class TenantDisponibiliteAPIView(APIView):
    """
    GET /tenants/v1/disponibilite/?sous_domaine=xxx -- vérification EN
    DIRECT (pendant la saisie, avant soumission) de la disponibilité
    d'un sous-domaine pour le formulaire de création de tenant. Revalidé
    de toute façon côté serveur à la soumission (TenantCreateSerializer)
    -- cet endpoint n'est qu'un retour immédiat pour l'UX, jamais la
    seule ligne de défense contre un doublon (fenêtre de course possible
    entre la vérification et la soumission réelle).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        sous_domaine = (request.query_params.get('sous_domaine') or '').strip().lower()
        if not sous_domaine:
            return Response({"detail": "Paramètre 'sous_domaine' requis."}, status=status.HTTP_400_BAD_REQUEST)
        format_valide = bool(re.match(r'^[a-z0-9-]+$', sous_domaine)) and len(sous_domaine) >= 3
        disponible = format_valide and not TenantService.exists_by_sous_domaine(sous_domaine)
        return Response({
            "sous_domaine": sous_domaine,
            "disponible": disponible,
            "format_valide": format_valide,
        })

    def put(self, request):
        formatReponse, stat, settings_token_actif = check_token_settings()
        if not stat:
            return Response(formatReponse, status=formatReponse['status'])
        
        # 1.2 Verification de la conformite du tenant par le sous-domaine dans l'URL
        ten, formatReponse = TenantService.get_tenant_by_sous_domaine_actif(request)
        if ten is None:
            return Response(formatReponse, int(formatReponse['status']))
        
        ###### 1. Verification de l'ensemble de doneees en entrée
        # 1.1 Verification de la conformite des doneees en entrée dans le serializer
        serializer = TenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # return Response(
        #     {
        #         'name':serializer.validated_data['name'],
        #         'sous_domaine':serializer.validated_data['sous_domaine'],
        #         # 'schema_name':serializer.validated_data['schema_name'],
        #         'description':serializer.validated_data['description'],
        #         'logo':serializer.validated_data['logo'],
        #         'settings':serializer.validated_data['settings'],
        #         'update_at': timezone.now()
        #     }
        # )
        # Sérialisation du tenant créé

        # 2. Préparation des données
        global domain_name
        domain_name = f"{serializer.validated_data['sous_domaine']}.{settings.MAIN_DOMAIN}"

        # Forcer l'utilisation du schéma public pour la création
        with schema_context('public'):
            try:
                tenant = TenantService.update_all_tenant_by_perform(
                    {
                        'id': ten.id,
                        'is_active': True
                    },
                    {
                        'name':serializer.validated_data['name'],
                        'sous_domaine':serializer.validated_data['sous_domaine'],
                        'description':serializer.validated_data['description'],
                        'logo':serializer.validated_data['logo'],
                        'settings':serializer.validated_data['settings'],
                        'update_at': timezone.now()
                    }
                )
                tenant.save()
                DomainService.update_all_domain_by_perform(
                    {
                        'tenant_id': tenant.id,
                    },
                    {
                        'domain': domain_name,
                    }
                )
            except ValidationError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({"detail": "Erreur interne."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Sérialisation du tenant créé
            tenant_data = TenantSerializer(tenant).data

            return Response({
                "tenant": tenant_data,  # utile si mot de passe généré automatiquement
            }, status=status.HTTP_201_CREATED)

