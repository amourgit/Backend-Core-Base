"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf import settings
from django.conf.urls.static import static 

# Personnalisation de l'espace admin (identique dans chaque schéma tenant) :
# permet de retrouver clairement toutes les apps CIVITAS NEWS, bien
# regroupées et étiquetées, dans une interface cohérente.
admin.site.site_header = 'Administration CIVITAS NEWS'
admin.site.site_title = 'CIVITAS NEWS'
admin.site.index_title = "Gestion de la plateforme"

schema_view = get_schema_view(
    openapi.Info(
        title="API Documentation",
        default_version='v1',
        description="API documentation for the project",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@example.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)


urlpatterns = [
    path('admin/', admin.site.urls),

    # API Documentation
    path('api/swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # API endpoints Shared
    path('api/token/', include('token_manager.urls')),
    path('api/tenants/', include('tenants.urls')),
    path('api/users/', include('users.urls')),
    path('api/domain/', include('domain.urls')),

    # API endpoints CIVITAS NEWS (domaines métier, isolés par tenant)
    path('api/referentiels/', include('referentiels.urls')),
    path('api/news/', include('news.urls')),
    path('api/commentaires/', include('commentaires.urls')),
    path('api/sondages/', include('sondages.urls')),
    path('api/liens/', include('liens.urls')),
    path('api/notifications/', include('notifications.urls')),
    path('api/journal/', include('journal.urls')),
    path('api/moderation/', include('moderation.urls')),
    path('api/statistiques/', include('statistiques.urls')),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
