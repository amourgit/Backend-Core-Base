from django.urls import path
# from rest_framework.routers import DefaultRouter
from . import views

# router = DefaultRouter()
# router.register(r'tenants', views.TenantViewSet, basename='tenant')
# router.register(r'domains', views.DomainViewSet, basename='domain')

urlpatterns = [
    # path('', include(router.urls)),
    path('', views.TenantCreateAPIView.as_view(), name='tenant-create'),
]