from django.shortcuts import render
from django.http import JsonResponse

# A view weather_data não será mais utilizada diretamente pelo frontend
# Mantenha-a se for usada por outras partes do backend ou para futura expansão
def home(request):
    return render(request, 'core/index.html')

# A view weather_data será esvaziada ou removida, pois o frontend fará a requisição direta.
# Por enquanto, vou deixá-la vazia para não quebrar outras dependências, se houver.
def weather_data(request):
    return JsonResponse({"message": "Requisição de clima agora é feita diretamente pelo frontend."})
