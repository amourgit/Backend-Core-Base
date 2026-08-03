from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    LogoutView,
    TokenSettingsViewSet,
    TokenManagerViewSet,
    SessionManagementView,
    checkTokenView
)

router = DefaultRouter()
router.register(r'settings', TokenSettingsViewSet, basename='token-settings')
router.register(r'tokens', TokenManagerViewSet, basename='token-manager')

urlpatterns = [
    # Routes d'authentification
    path('', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='token_logout'),
    
    # Routes de gestion des sessions
    path('sessions/', SessionManagementView.as_view(), name='session-list'),
    # path('sessions/<int:session_id>/', SessionManagementView.as_view(), name='session-detail'),
    # path('sessions/revoke/<int:session_id>/', SessionManagementView.as_view(), name='session-revoke'),

    # Routes de verification des tokens
    path('check-token/', checkTokenView.as_view(), name='check-token'),
    
    # Routes de gestion des tokens
    path('', include(router.urls)),
]
