import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from django.db.models import Q
from tenants.models import Tenant, TenantDocumentRequis, TenantDocumentGenerique, TenantTutelle, StatutTutelle
from .serializers import (
    TenantSerializer,
    TenantCreateSerializer,
    TenantPublicSerializer,
    TenantIdentiteSerializer,
    TenantProfilPublicSerializer,
    TenantInformationsPrimairesSerializer,
    TenantDocumentRequisSerializer,
    TenantDocumentGeneriqueSerializer,
    TypeDocumentRequisCatalogueSerializer,
    TenantTutelleSerializer,
    TenantTutelleCreateSerializer,
    TenantTutelleMotifSerializer,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.core.exceptions import ValidationError
from django_tenants.utils import schema_context
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .services import TenantService, TenantDossierService, TenantTutelleService
from .mixins import SharedTenantScopedModelViewSet
from common.drf import SocleModelViewSet
from .permissions import EstAdministrateurDuTenant
from token_manager.api.v1.utils import check_token_settings
from token_manager.api.v1.permissions import IsAccessTokenTenant
from domain.api.v1.services import DomainService
from django.utils.text import slugify
from django.conf import settings
from django.utils import timezone
from common.admin import est_schema_public


class TenantCourantMixin:
    """
    Résolution du tenant COURANT d'une requête (`request.tenant`, posé par
    `tenants.middleware.TenantMiddleware`) pour les vues singleton dont
    la ressource EST le tenant (ou sa fiche) : renvoie `(tenant, None)` ou
    `(None, Response 400)`. Le tenant n'est jamais lu depuis le corps ni
    l'URL -- un client ne peut donc pas viser un autre tenant que celui de
    son token (voir aussi `IsAccessTokenTenant`).
    """

    def _tenant_ou_erreur(self, request):
        tenant = getattr(request, 'tenant', None)
        if not isinstance(tenant, Tenant) or tenant.pk is None:
            return None, Response({"detail": "Tenant non résolu pour cette requête."}, status=status.HTTP_400_BAD_REQUEST)
        return tenant, None


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
                'logo': openapi.Schema(type=openapi.TYPE_FILE, description="Logo de l'organisation (optionnel, multipart/form-data)"),
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
                    logo=serializer.validated_data.get('logo'),
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


class TenantProfilPublicAPIView(APIView):
    """
    GET /tenants/v1/profil-public/<sous_domaine>/ -- profil PUBLIC d'UNE
    organisation active : identité de l'annuaire + extrait public de sa
    fiche (`fiche_publique`, liste blanche -- voir
    `TenantFichePubliqueSerializer`). Alimente la page de détails d'une
    organisation simplement CONSULTÉE (ni connectée dedans, ni
    administrateur) côté frontend.

    Même contrat d'accès que l'annuaire (`TenantCreateAPIView.get`) :
    AllowAny, sans authentification -- rien de sensible n'y est exposé.
    404 si le sous-domaine est inconnu OU si l'organisation est inactive
    (indistinguables, comme pour l'annuaire qui ne liste que les actives).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, sous_domaine):
        tenant = Tenant.objects.filter(is_active=True, sous_domaine=sous_domaine.lower()).first()
        if tenant is None:
            return Response({"detail": "Organisation introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TenantProfilPublicSerializer(tenant, context={'request': request}).data)


class TenantIdentiteAPIView(TenantCourantMixin, APIView):
    """
    GET/PATCH /tenants/v1/identite/ -- identité PUBLIQUE (nom,
    description, logo) du TENANT COURANT : ressource singleton, sans
    identifiant dans l'URL, exactement comme `informations-primaires/`.

    Accès réservé à l'ADMINISTRATEUR du tenant (`EstAdministrateurDuTenant`)
    dont le token appartient bien à CE tenant (`IsAccessTokenTenant`) :
    un administrateur d'une autre organisation n'a aucun droit ici, même
    en envoyant le sous-domaine d'un autre tenant. Modification PARTIELLE
    uniquement (PATCH) ; JSON ou multipart (nécessaire pour le logo).
    """
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]

    def get(self, request):
        tenant, erreur = self._tenant_ou_erreur(request)
        if erreur:
            return erreur
        return Response(TenantIdentiteSerializer(tenant, context={'request': request}).data)

    def patch(self, request):
        tenant, erreur = self._tenant_ou_erreur(request)
        if erreur:
            return erreur
        serializer = TenantIdentiteSerializer(tenant, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        tenant = TenantService.mettre_a_jour_identite(tenant, serializer.validated_data)
        return Response(TenantIdentiteSerializer(tenant, context={'request': request}).data)


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


class TenantInformationsPrimairesAPIView(TenantCourantMixin, APIView):
    """
    GET/PUT/PATCH /tenants/v1/informations-primaires/ -- fiche d'identité
    primaire du TENANT COURANT (résolu via `request.tenant`, voir
    `tenants.middleware.TenantMiddleware`), créée à la volée au premier
    accès (voir `TenantDossierService.get_or_create_informations`) : un
    tenant n'a par construction QU'UNE seule fiche (`OneToOneField` sur
    `TenantInformationsPrimaires`), donc jamais besoin d'identifiant dans
    l'URL.

    Accès réservé à l'ADMINISTRATEUR du tenant (`EstAdministrateurDuTenant`,
    en plus de `IsAccessTokenTenant` qui vérifie que le token appartient
    bien à CE tenant) : une fiche d'identité légale/administrative n'est
    pas une donnée à exposer à n'importe quel membre du tenant.
    """
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]

    def get(self, request):
        tenant, erreur = self._tenant_ou_erreur(request)
        if erreur:
            return erreur
        informations = TenantDossierService.get_or_create_informations(tenant)
        return Response(TenantInformationsPrimairesSerializer(informations).data)

    def _enregistrer(self, request, partial):
        tenant, erreur = self._tenant_ou_erreur(request)
        if erreur:
            return erreur
        informations = TenantDossierService.get_or_create_informations(tenant)
        serializer = TenantInformationsPrimairesSerializer(informations, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        # Traçabilité sûre du point de vue schéma -- voir la note
        # d'architecture en tête de tenants/models.py.
        if est_schema_public():
            serializer.save(modifie_par=request.user)
        else:
            nom = request.user.get_username() or str(request.user.pk)
            serializer.save(modifie_par_systeme=f"tenant:{tenant.schema_name}:{nom}")
        return Response(serializer.data)

    def put(self, request):
        return self._enregistrer(request, partial=False)

    def patch(self, request):
        return self._enregistrer(request, partial=True)


class TenantDocumentRequisViewSet(SharedTenantScopedModelViewSet):
    """
    CRUD des soumissions de documents du catalogue fixe pour le TENANT
    COURANT -- voir `SharedTenantScopedModelViewSet`
    (tenants/api/v1/mixins.py) pour le filtrage/la traçabilité, et
    `TenantDocumentRequisSerializer` pour les contraintes (taille,
    formats, périodicité) exposées au frontend.
    """
    serializer_class = TenantDocumentRequisSerializer
    queryset = TenantDocumentRequis.objects.select_related('tenant').all()
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]


class TenantDocumentGeneriqueViewSet(SharedTenantScopedModelViewSet):
    """CRUD des documents génériques (libres, hors catalogue fixe) pour
    le TENANT COURANT."""
    serializer_class = TenantDocumentGeneriqueSerializer
    queryset = TenantDocumentGenerique.objects.select_related('tenant').all()
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]


class TenantDocumentRequisCatalogueAPIView(APIView):
    """
    GET /tenants/v1/catalogue-documents-requis/ -- catalogue fixe des
    documents demandés par la plateforme (voir `TypeDocumentRequis` /
    `ContraintesDocumentRequis`, tenants/models.py), avec leurs
    contraintes. Public (`AllowAny`) : ne révèle aucune donnée propre à
    un tenant, uniquement les EXIGENCES de la plateforme -- utile dès
    l'onboarding, avant même la création d'un compte.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        serializer = TypeDocumentRequisCatalogueSerializer(TenantDossierService.construire_catalogue(), many=True)
        return Response(serializer.data)


class TenantDossierAPIView(APIView):
    """
    GET /tenants/v1/dossier/ -- vue d'ensemble du dossier du TENANT
    COURANT : fiche d'identité + checklist des documents requis (fournis
    ou manquants, voir `TenantDossierService.construire_checklist_documents_requis`)
    + documents génériques, en UN seul appel. Répond aux deux objectifs
    de ce chantier : une vue plateforme complète ("nos études") et une
    checklist claire pour le tenant lui-même de ce qu'il lui reste à
    fournir ("utile pour elle").
    """
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]

    def get(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({"detail": "Tenant non résolu pour cette requête."}, status=status.HTTP_400_BAD_REQUEST)

        dossier = TenantDossierService.construire_dossier(tenant)
        checklist = [
            {
                'type': entree['type'],
                'libelle': entree['libelle'],
                'extensions_autorisees': entree['extensions_autorisees'],
                'taille_max_mo': entree['taille_max_mo'],
                'periodicite': entree['periodicite'],
                'periodicite_libelle': entree['periodicite_libelle'],
                'fourni': entree['fourni'],
                'soumissions': TenantDocumentRequisSerializer(
                    entree['soumissions'], many=True, context={'request': request},
                ).data,
            }
            for entree in dossier['documents_requis']
        ]
        return Response({
            'tenant': TenantPublicSerializer(tenant).data,
            'informations_primaires': TenantInformationsPrimairesSerializer(dossier['informations']).data,
            'documents_requis': checklist,
            'documents_generiques': TenantDocumentGeneriqueSerializer(
                dossier['documents_generiques'], many=True, context={'request': request},
            ).data,
        })


class TenantTutelleViewSet(SocleModelViewSet):
    """
    Relations de tutelle du TENANT COURANT -- voir
    `tenants.models.TenantTutelle` pour le workflow de double
    consentement et la logique de cascade flexible. Contrairement aux
    documents (un seul champ `tenant`), une tutelle en engage DEUX : le
    queryset est filtré "le tenant courant apparaît dans l'un ou l'autre
    rôle" plutôt que via `SharedTenantScopedModelViewSet`
    (tenants/api/v1/mixins.py, pensé pour un seul champ `tenant`).

      - `list`/`retrieve` : toutes les relations (tous statuts) où le
        tenant courant est impliqué (tuteur, sous tutelle ou initiateur).
      - `create` : propose une tutelle (voir `TenantTutelleCreateSerializer`) --
        le tenant courant est TOUJOURS l'initiateur.
      - `valider`/`refuser` : réservées au tenant DESTINATAIRE (celui qui
        n'a PAS initié) d'une proposition EN_ATTENTE_VALIDATION.
      - `rompre` : ouverte aux DEUX parties d'une relation ACTIVE/SUSPENDUE.
      - `en_attente` : uniquement les propositions où le tenant courant
        doit précisément agir (lui, le destinataire).
      - `hierarchie` : chaîne ascendante + descendants du tenant courant.

    Pas de `update`/`destroy` génériques (voir `http_method_names`) :
    toute évolution passe par les transitions métier explicites
    ci-dessus, jamais par un PATCH/DELETE qui contournerait le
    consentement de l'autre partie ou l'historique du Socle de
    Traçabilité.
    """
    permission_classes = [IsAuthenticated, IsAccessTokenTenant, EstAdministrateurDuTenant]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        tenant = getattr(self.request, 'tenant', None)
        if not tenant:
            return TenantTutelle.objects.none()
        return TenantTutelleService.relations_du_tenant(tenant).filter(supprime_le__isnull=True)

    def get_serializer_class(self):
        if self.action == 'create':
            return TenantTutelleCreateSerializer
        if self.action in ('refuser', 'rompre'):
            return TenantTutelleMotifSerializer
        return TenantTutelleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        relation = serializer.save()
        return Response(TenantTutelleSerializer(relation).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _erreur_validation(exc):
        messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
        return Response({'detail': messages}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def valider(self, request, pk=None):
        relation = self.get_object()
        if relation.tenant_destinataire.id != request.tenant.id:
            return Response(
                {'detail': "Seul le tenant destinataire de cette proposition peut la valider."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            relation.valider()
        except ValidationError as exc:
            return self._erreur_validation(exc)
        return Response(TenantTutelleSerializer(relation).data)

    @action(detail=True, methods=['post'])
    def refuser(self, request, pk=None):
        relation = self.get_object()
        if relation.tenant_destinataire.id != request.tenant.id:
            return Response(
                {'detail': "Seul le tenant destinataire de cette proposition peut la refuser."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation.refuser(motif=serializer.validated_data.get('motif', ''))
        except ValidationError as exc:
            return self._erreur_validation(exc)
        return Response(TenantTutelleSerializer(relation).data)

    @action(detail=True, methods=['post'])
    def rompre(self, request, pk=None):
        relation = self.get_object()
        tenant = request.tenant
        if tenant.id not in (relation.tenant_tutelle_id, relation.tenant_sous_tutelle_id):
            return Response(
                {'detail': "Seules les deux parties d'une tutelle peuvent y mettre fin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            relation.rompre(motif=serializer.validated_data.get('motif', ''))
        except ValidationError as exc:
            return self._erreur_validation(exc)
        return Response(TenantTutelleSerializer(relation).data)

    @action(detail=False, methods=['get'])
    def en_attente(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({"detail": "Tenant non résolu pour cette requête."}, status=status.HTTP_400_BAD_REQUEST)
        relations = TenantTutelleService.en_attente_de_validation_par(tenant)
        return Response(TenantTutelleSerializer(relations, many=True).data)

    @action(detail=False, methods=['get'])
    def hierarchie(self, request):
        tenant = getattr(request, 'tenant', None)
        if not tenant:
            return Response({"detail": "Tenant non résolu pour cette requête."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'tenant': TenantPublicSerializer(tenant).data,
            'ascendants': TenantPublicSerializer(TenantTutelleService.chaine_ascendante(tenant), many=True).data,
            'descendants': TenantPublicSerializer(TenantTutelleService.descendants(tenant), many=True).data,
        })

