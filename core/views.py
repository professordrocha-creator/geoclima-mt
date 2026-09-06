# core/views.py
import base64
import json
from io import BytesIO

from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.utils.text import slugify

from climate.calculadora_exports import gerar_workbook_validacao
from climate.calculadora_narrativas import gerar_interpretacoes
from climate.calculadora_validacao import calcular_validacao
from climate.data_import import ErroImportacao, processar_arquivo
from climate.validation import MINIMO_PARES

from .forms import CalculadoraValidacaoForm

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


def calculadora(request):
    """
    Calculadora de validação CHIRPS × pluviômetro (pública, sem login,
    fora do PDF original — pedido do usuário depois da home nova). A
    metodologia do Artigo 1 (climate/validation.py, Etapa 7.2) exposta
    pra qualquer pesquisador comparar o dado medido no pluviômetro
    dele contra o CHIRPS de um município — sem cadastrar nada.

    Opção A de armazenamento (decisão explícita, ver docs/DECISOES.md):
    NADA é salvo em disco/banco/sessão, nem temporariamente — tudo
    acontece num único request/response. O .xlsx de exportação é
    gerado em memória e embutido na própria página como link de
    download (data URI em base64), então o usuário recebe o resultado
    completo (métricas, gráfico, Excel) numa passada só, sem precisar
    reenviar o arquivo pra baixar a planilha depois.
    """
    contexto = {"form": CalculadoraValidacaoForm(), "minimo_pares": MINIMO_PARES}

    if request.method == "POST":
        form = CalculadoraValidacaoForm(request.POST, request.FILES)
        contexto["form"] = form

        if form.is_valid():
            municipio = form.cleaned_data["municipio"]
            arquivo = form.cleaned_data["arquivo"]

            try:
                registros, erros_linha = processar_arquivo(arquivo)
            except ErroImportacao as exc:
                form.add_error("arquivo", str(exc))
            else:
                resultado = calcular_validacao(registros, municipio)

                if resultado["granularidade"] is None:
                    form.add_error("arquivo", "Não encontrei pelo menos 2 datas distintas no arquivo — impossível calcular.")
                elif resultado["metricas"] is None:
                    form.add_error(
                        None,
                        f"Não há pelo menos {MINIMO_PARES} dias/meses em comum entre o arquivo enviado e o "
                        f"CHIRPS de {municipio.nome}/{municipio.uf} no período informado. Confira as datas do "
                        "arquivo e se o município escolhido é o correto.",
                    )
                else:
                    workbook = gerar_workbook_validacao(municipio, resultado)
                    buffer = BytesIO()
                    workbook.save(buffer)
                    excel_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
                    nome_arquivo_excel = (
                        f"validacao_{slugify(municipio.nome)}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
                    )

                    # Django não tem filtro de subtração no template — a
                    # diferença (pra coluna "Diferença" da tabela) é
                    # calculada aqui, não no template.
                    pares_tabela = [
                        {"data": data, "chirps": chirps, "local": local, "diferenca": chirps - local}
                        for data, chirps, local in resultado["pares"]
                    ]

                    # Dado bruto pros 6 gráficos: montado em Python (json.dumps,
                    # não interpolação de float no template) pra não cair na
                    # armadilha de {{ valor }} quebrando com vírgula do pt-br —
                    # ver docs/DECISOES.md. Um blob só, o JS deriva os formatos
                    # específicos de cada gráfico (dispersão, série temporal,
                    # resíduos, acumulado, histograma, erro×magnitude) a partir
                    # dele — nenhum cálculo novo acontece no JS.
                    dados_graficos = {
                        "granularidade": resultado["granularidade"],
                        "pares": [
                            {
                                "data": data.isoformat(),
                                "chirps": round(chirps, 2),
                                "local": round(local, 2),
                                "diferenca": round(chirps - local, 2),
                            }
                            for data, chirps, local in resultado["pares"]
                        ],
                        "histograma": resultado["histograma"],
                    }

                    contexto.update({
                        "municipio": municipio,
                        "resultado": resultado,
                        "pares_tabela": pares_tabela,
                        "excel_base64": excel_base64,
                        "nome_arquivo_excel": nome_arquivo_excel,
                        "erros_linha": erros_linha[:10],
                        "total_erros_linha": len(erros_linha),
                        "dados_graficos_json": json.dumps(dados_graficos, ensure_ascii=False),
                        "interpretacoes_json": json.dumps(gerar_interpretacoes(resultado), ensure_ascii=False),
                    })

    return render(request, "core/calculadora.html", contexto)
