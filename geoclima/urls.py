# geoclima/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('core.urls')),
    path('api/', include('api.urls')),
    path('accounts/', include('accounts.urls')),
    path('painel/', include('dashboard.urls')),
    path('painel/fazendas/', include('farms.urls')),
    path('painel/estacoes/', include('stations.urls')),
    path('painel/chuva/', include('climate.urls')),
    path('painel/usuarios/', include('accounts.urls_gestao')),
    path('admin/', admin.site.urls),
]
