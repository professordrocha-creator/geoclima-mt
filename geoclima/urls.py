# geoclima/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('core.urls')),
    path('api/', include('api.urls')),
    path('accounts/', include('accounts.urls')),
    path('painel/', include('dashboard.urls')),
    path('admin/', admin.site.urls),
]
