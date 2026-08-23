# climate/correction.py
"""
Correção local / calibração regional do CHIRPS (Etapa 7.4). Usa o MBE
(viés médio) já calculado pela validação estatística (Etapa 7.2,
climate/validation.py) — não recalcula nada novo, só aplica a correção
descrita no PDF:

    CHIRPS estimou 100 mm; estação local registrou 112 mm (viés de
    -12 mm, ou seja, CHIRPS sub-estima); "sistema aprende essa
    diferença regional" e passa a corrigir estimativas futuras do
    CHIRPS somando o viés de volta.

MBE = média(chirps - local) (ver validation.py). Corrigir um valor de
CHIRPS é subtrair o MBE: valor_corrigido = valor_chirps - mbe.

Só é possível corrigir uma estação que já tenha uma ChirpsValidation
calculada (n_pares >= MINIMO_PARES) — sem isso não há viés confiável
pra aplicar. Não persiste nada: é sempre calculado on-the-fly a partir
do ChirpsData bruto (que segue intocado) e do MBE mais recente, do
mesmo jeito que a ChirpsValidation em si é "sempre o estado atual", não
um histórico.
"""
from .models import ChirpsData

DIAS_SERIE_CORRIGIDA = 10


def corrigir_valor(valor_chirps, mbe):
    """Aplica a correção de viés a um valor de CHIRPS. Chuva não pode ser negativa."""
    return max(0.0, valor_chirps - mbe)


def serie_chirps_corrigida(station, dias=DIAS_SERIE_CORRIGIDA):
    """
    Últimos `dias` valores de CHIRPS do município da fazenda da estação,
    brutos e corrigidos lado a lado. Devolve [] se a estação ainda não
    tiver ChirpsValidation (sem viés calculado, sem o que corrigir).
    """
    validacao = getattr(station, "chirps_validation", None)
    if validacao is None:
        return []

    municipio = station.farm.municipio
    registros = ChirpsData.objects.filter(municipio=municipio).order_by("-date")[:dias]

    return [
        {
            "date": registro.date,
            "bruto": registro.value,
            "corrigido": corrigir_valor(registro.value, validacao.mbe),
        }
        for registro in reversed(registros)
    ]
