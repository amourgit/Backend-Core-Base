from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from tenants.models import Tenant
from .serializers import TenantSerializer, TenantCreateSerializer
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
    permission_classes = [AllowAny]  # accessible publiquement
    @swagger_auto_schema(
        operation_description="Créer un nouveau tenant avec un administrateur",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['name', 'sous_domaine', 'admin_email'],
            properties={
                'name': openapi.Schema(type=openapi.TYPE_STRING, description="Nom du tenant"),
                'sous_domaine': openapi.Schema(type=openapi.TYPE_STRING, description="Sous-domaine pour le tenant (ex: 'mon-tenant' pour mon-tenant.localhost)"),
                'admin_email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL, description="Email de l'administrateur"),
                'admin_password': openapi.Schema(type=openapi.TYPE_STRING, description="Mot de passe de l'administrateur (optionnel, généré automatiquement si non fourni)"),
                'admin_username': openapi.Schema(type=openapi.TYPE_STRING, description="Nom d'utilisateur de l'administrateur (optionnel, généré à partir de l'email si non fourni)"),
            },
        ),
        responses={
            201: openapi.Response(
                description="Tenant créé avec succès",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'tenant': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'id': openapi.Schema(type=openapi.TYPE_INTEGER),
                                'name': openapi.Schema(type=openapi.TYPE_STRING),
                                'sous_domaine': openapi.Schema(type=openapi.TYPE_STRING),
                                'schema_name': openapi.Schema(type=openapi.TYPE_STRING),
                                'is_active': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                                'created_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                                'updated_at': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                            }
                        ),
                        'admin_credentials': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'username': openapi.Schema(type=openapi.TYPE_STRING),
                                'password': openapi.Schema(type=openapi.TYPE_STRING),
                            }
                        ),
                    }
                )
            ),
            400: "Données invalides",
            500: "Erreur interne du serveur"
        }
    )
    def post(self, request):
        # Validation des données avec le serializer
        serializer = TenantCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Forcer l'utilisation du schéma public pour la création
        with schema_context('public'):
            try:
                tenant, domain, admin_credentials = Tenant.create_with_domain(
                    name=serializer.validated_data['name'],
                    sous_domaine=serializer.validated_data['sous_domaine'],
                    admin_email=serializer.validated_data['admin_email'],
                    admin_password=serializer.validated_data.get('admin_password'),
                    admin_username=serializer.validated_data.get('admin_username'),
                )
            except ValidationError as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({"detail": "Erreur interne."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Sérialisation du tenant créé
            tenant_data = TenantSerializer(tenant).data

            return Response({
                "tenant": tenant_data,
                "admin_credentials": admin_credentials  # utile si mot de passe généré automatiquement
            }, status=status.HTTP_201_CREATED)

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

