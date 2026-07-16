# Histórico de Desenvolvimento GeoClima MT

## 2026-06-19 - Unificação da Home com Open-Meteo

**Modificações:**
- A integração da Home foi redesenhada para utilizar diretamente as APIs gratuitas da Open-Meteo (Forecast API e Air Quality API).
- No backend (Django `views.py`):
    - A view `weather_data` foi atualizada para receber latitude e longitude via GET.
    - Foram adicionadas chamadas `requests` para as APIs da Open-Meteo, buscando dados de previsão (temperatura atual, umidade, sensação térmica, pressão, velocidade do vento, código do tempo, máximas/mínimas diárias, índice UV, nascer/pôr do sol) e qualidade do ar (US AQI).
    - Os dados foram unificados em um `JsonResponse` limpo. Em caso de falha, um `JsonResponse` com o erro e status 400 é retornado.
    - Mapeamento de `weather_code` para descrições amigáveis e ícones foi implementado diretamente na view para o backend.
- No frontend (JavaScript e HTML em `index.html`):
    - A barra lateral esquerda (Filtros CHIRPS) foi removida.
    - O título principal foi alterado para "GeoClima MT".
    - O `fetch()` do JavaScript foi ajustado para consumir o novo JSON unificado do backend.
    - Os dados recebidos são injetados diretamente nos cards da interface (Temperatura atual, Sensação, Umidade, Vento, Pressão, AQI, UV, Nascer/Pôr do Sol, Previsão por Hora e Previsão de 7 dias).
    - O mapeamento de `weather_code` para textos comerciais amigáveis e ícones foi adicionado no JavaScript para renderização no frontend.
    - A lógica de geolocalização foi simplificada para apenas obter a localização do usuário e carregar os dados climáticos, removendo a inicialização e interação com o mapa Leaflet para esta funcionalidade específica da Home.

## 2026-06-19 - Ajuste de Layout e Mapa no Frontend

**Modificações:**
- A requisição para a Open-Meteo foi movida diretamente para o frontend (JavaScript em `core/templates/core/index.html`), removendo a dependência da rota Django para o `fetch` dos dados climáticos.
- O JavaScript agora faz o `fetch` para as URLs diretas da Open-Meteo para obter os dados de previsão e qualidade do ar, e em seguida, injeta esses dados diretamente nos cards da Home.
- A view `weather_data` no Django (`core/views.py`) foi esvaziada e ajustada para indicar que a requisição de clima agora é feita diretamente pelo frontend.
- O layout da Home foi reestruturado para ser responsivo, utilizando classes Bootstrap (`col-12`, `col-md-7`, `col-lg-8`, `col-md-5`, `col-lg-4`) para organizar o bloco de clima e o mapa lado a lado.
- A altura do card de clima atual e do mapa foi fixada em `380px` (via style inline e CSS) para manter a simetria visual e corrigir problemas de renderização do mapa.
- No JavaScript, a inicialização do mapa (`L.map`) foi corrigida para ocorrer no carregamento da página, antes da geolocalização.
- O comando `map.invalidateSize()` foi adicionado no JavaScript após o `map.setView()` (e no tratamento de erro da geolocalização) para forçar o Leaflet a recalcular o tamanho e preencher o novo espaço responsivo, resolvendo o problema de mapa não aparecendo e barra de rolagem horizontal.
- A informação de "Visibilidade" foi ajustada para exibir `-- km` por padrão, pois a API da Open-Meteo não fornece este dado na configuração atual.

## 2026-06-19 - Enriquecimento de Dados Climáticos e Cards

**Modificações:**
- A URL do fetch da Forecast API no JavaScript foi atualizada para incluir `precipitation,visibility` em `&current=` e `precipitation_sum,wind_gusts_10m_max` em `&daily=`.
- O card de Visibilidade foi corrigido para receber `current.visibility` e dividir por 1000 para exibir em "km" no frontend.
- Novos cartões foram adicionados na seção de micro-detalhes para exibir:
    - **Chuva (1h)**: Utilizando `current.precipitation`.
    - **Chuva (Dia)**: Utilizando `daily.precipitation_sum[0]`.
    - **Rajada Máxima**: Utilizando `daily.wind_gusts_10m_max[0]`.
- O bloco "Por Hora" foi atualizado para preencher visualmente com uma sequência horizontal de mini-cards (Hora e Temperatura) usando `hourly.temperature_2m` e `hourly.weather_code` para as próximas 8 horas a partir do horário atual.
- A estrutura HTML e CSS foram mantidas limpas e responsivas para acomodar os novos dados e cards.