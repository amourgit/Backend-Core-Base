from django.urls import path, include

urlpatterns = [
    path('v1/', include('journal.api.v1.urls')),
]
