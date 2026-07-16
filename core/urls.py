from django.urls import path
from .views import home, weather_data

urlpatterns = [
    path('', home, name='home'),
    path('weather-data/', weather_data, name='weather_data'),
]
