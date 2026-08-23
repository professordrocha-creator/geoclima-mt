# core/views.py
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


def ajuda(request):
    """
    Manual de uso do sistema (pedido do usuário, fora do escopo do PDF —
    ver docs/DECISOES.md). Página pública (não @login_required): ajuda
    quem ainda não tem conta a entender o que o sistema faz antes de se
    cadastrar, e quem já usa o sistema quando tiver dúvida. Estende
    `base.html` (mesmo layout/navbar de accounts/dashboard), não o
    template standalone da Home.
    """
    return render(request, "core/ajuda.html")
