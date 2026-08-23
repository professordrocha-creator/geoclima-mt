from django.urls import path
from .views import ajuda, home, weather_data

urlpatterns = [
    path('', home, name='home'),
    path('weather-data/', weather_data, name='weather_data'),
    path('ajuda/', ajuda, name='ajuda'),
]
