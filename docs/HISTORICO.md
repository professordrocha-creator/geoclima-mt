# Histórico de Desenvolvimento — GeoClima MT

> Changelog do projeto. As entradas de 2026-06-19 foram migradas de
> `requisitos/requisitos.md` (arquivo original mantido intacto no repo).

## 2026-09-01 (continuação 4) — Clique no mapa da home seleciona município (point-in-polygon PostGIS)

**Contexto:** pedido do usuário — clicar em qualquer ponto do mapa
principal da home deve funcionar como escolher a cidade no dropdown,
sem exigir o menu. Endpoint novo de point-in-polygon + reaproveitamento
total do que já existia (`aplicarSelecaoMunicipio`/`populateMunicipios`,
zero lógica duplicada).

**Endpoint**: `GET /api/municipio-por-ponto/?lat=&lon=` (`api/views.py`/
`api/urls.py`, mesmo padrão `JsonResponse` dos vizinhos) — `ST_Intersects`
nativo do PostGIS (`geom__intersects`), filtrado a `uf="MT"`. `null` se o
ponto cair fora de MT.

**Ajuste sobre o plano original**: usar `intersects` em vez de `contains`
desde o início (decisão do usuário) — `contains` exclui a borda exata do
polígono, e um clique/toque de usuário perto de uma divisa municipal é
comum o bastante pra virar falso-negativo incômodo. Achado real durante
o teste que confirma a escolha: um ponto exatamente sobre a fronteira
Cuiabá/Várzea Grande (lat=-15.741986, lon=-56.110910, calculado via
interseção real das bordas dos 2 polígonos) devolve `[]` com `contains`
e `['Cuiabá', 'Várzea Grande']` com `intersects` — o `.first()` do
ORM pega um dos dois, aceitável.

**Frontend** (`core/templates/core/index.html`): `map.on("click", ...)`
registrado em `initializeMap()`, chama `handleMapClick(lat, lon)` (nova,
~20 linhas) — busca o endpoint, e se achou município repassa pra
`populateMunicipios(uf, codigo_ibge)` (sincroniza o `<select>`, já
existia, não dispara nada sozinha) e `aplicarSelecaoMunicipio(id)`
(a MESMA função que o `change` do dropdown chama — contorno, centralização,
todos os indicadores Fase 1/2, botão de exportar). Clique fora de MT: só
atualiza o texto de `#localitySelectorHint` com um aviso, sem quebrar
nada. `#map { cursor: pointer; }` sinaliza que é clicável (especificidade
de ID vence o `cursor: grab` do Leaflet). Contorno não acumula —
`aplicarSelecaoMunicipio` já removia a camada anterior antes desta
entrada, comportamento herdado de graça.

**Testado**: `curl` direto no endpoint — centroides de Tangará, Cáceres
e Cuiabá cada um retornando o município certo; o ponto exato na
fronteira Cuiabá/Várzea Grande confirmando `intersects` (Várzea Grande,
via `.first()`) onde `contains` teria dado `null`; um ponto fora de MT
(São Paulo capital) devolvendo `null` com HTTP 200 (não erro); parâmetros
inválidos devolvendo 400. Equivalência clique↔dropdown confirmada por
inspeção de código (não só pela simetria de design): os dois caminhos
convergem na mesma chamada `aplicarSelecaoMunicipio(id)`, sem branch
divergente em nenhum dos dois. `manage.py check` limpo, JS revalidado
com `node --check`.

## 2026-09-01 (continuação 3) — Exportação de dados (.xlsx) por município, pública, com metadados e citação CHIRPS

**Contexto:** pedido do usuário, fora do roadmap — dar reprodutibilidade
científica e utilidade pública real aos indicadores da home: um botão
"Exportar dados" que baixa tudo (dado bruto + indicadores calculados +
metadados/citação) num arquivo só, pra pesquisador/gestor reusar fora
da plataforma. Plano (7 abas) revisado e aprovado pelo usuário antes de
codar.

**`climate/municipio_exports.py`** (novo, espelha `farms/exports.py`
da Etapa 11 — `openpyxl` já dependência, zero lib nova): 7 abas —
Metadados (fonte CHIRPS, resolução ~0,05°/~5km, cobertura desde 1981,
município/UF/código IBGE/centroide, período dos dados, data de
extração, **citação recomendada** — Funk et al. 2015, Scientific Data
— e nota de extração via GEE), Resumo (Indicadores Atuais — snapshot
de tudo que a home mostra hoje, sem recalcular), Precipitação Diária
(série bruta completa, ~16.649 linhas), SPI (4 escalas, ~2.171 linhas),
Climatologia Mensal (12 linhas), Indicadores Anuais (1 linha por ano —
total, dias chuvosos nos 3 limiares, intensidade, veranico máximo,
juntos numa tabela só), e Tendências (Mann-Kendall + Sen's Slope — os
4 testes já feitos, com S/Z/p-valor/significância completos, não só o
slope).

**Adição pequena aprovada**: coluna "Interpretação" na aba de
Tendências, com a mesma frase honesta que já aparece nos gráficos da
home (achado significativo nomeia a direção; não-significativo nunca
finge que é). Implementada como reuso de verdade, não duplicação —
`climate.municipio_indicators.interpretar_tendencia` (novo, público)
é a MESMA lógica que `renderizarDestaqueTendencia` (JS) já usava,
promovida a uma função Python única reaproveitada aqui. A versão JS
continua existindo à parte (navegador não roda Python) — duplicação
inevitável entre as duas linguagens, mas não entre dois lugares no
mesmo lado do sistema.

**Endpoint**: `GET /api/municipios/<id>/exportar/` — devolve o `.xlsx`
direto (`HttpResponse` + `Content-Disposition`, mesma técnica de
`farms/views.py` da Etapa 11), nome
`CHIRPS_<município-slug>_<UF>_<AAAAMMDD>.xlsx`. Município sem nenhum
`ChirpsData` devolve 404 em texto simples ANTES de gerar qualquer
workbook — nunca um `.xlsx` vazio/quebrado.

**Frontend**: botão "Exportar dados" no cabeçalho da seção de
indicadores (FASE 1) — desabilitado (`disabled`, `aria-disabled`) até
`renderizarIndicadoresClimaticos` confirmar que o município tem CHIRPS
(mesmo fetch que a seção já faz, sem chamada extra), aí vira um link
direto pro endpoint — o navegador baixa via `Content-Disposition`
nativo, sem `fetch`/blob no JS.

**Bug pego no teste, corrigido antes de mandar o arquivo**: o nome da
aba de tendências ("Tendências (Mann-Kendall + Sen's Slope)", 40
caracteres) excedia o limite de 31 caracteres do Excel — `openpyxl`
avisou (`UserWarning`) na geração. Encurtado pra "Tendências
(Mann-Kendall)" (26 caracteres); revalidado que todas as 7 abas ficam
dentro do limite.

**Testado**: gerado e inspecionado o arquivo de Cáceres de ponta a
ponta (`load_workbook` de volta, conferindo linha a linha) — os 4
resultados de tendência batem exatamente com os já validados nas
entradas anteriores (total −4,0149 mm/ano p=0,0113 sig.; dias chuvosos
−0,4 dias/ano p=0,0102 sig.; intensidade −0,0054 p=0,475 "Estável";
veranico +0,2778 dias/ano p=0,0049 sig., "aumento"). Endpoint testado
via `curl` (headers corretos, `Content-Disposition`) e com
Adamantina/SP (sem CHIRPS): 404 em texto, não um arquivo quebrado.
`manage.py check` limpo, JS revalidado com `node --check`.

**Contexto:** os p-valores calculados na entrada anterior (veranico e
dias chuvosos) ainda não apareciam na home — só a série bruta. Pedido
explícito do usuário, com 3 regras de comunicação: nunca dar a
entender tendência onde o teste não sustenta; nomear "não
significativo" quando for o caso (dias chuvosos); tratar "estável" como
resultado, não como ausência (intensidade).

**Backend** (`climate/municipio_indicators.py`) — `dias_chuvosos_serie_anual`
e `veranico_maximo_serie_anual` mudaram de forma (`{ano: valor}` direto
→ `{"serie": {...}, "tendencia": {...} ou None}`, mesmo formato que
`intensidade_serie_anual` já usava desde a entrada anterior) — cada
limiar de dias chuvosos (1/5/10mm) ganha sua PRÓPRIA tendência
(reaproveita `_tendencia_de_serie`, já genérico). Único consumidor
dessas duas funções era `api/views.py:municipio_series_anuais`
(conferido via grep antes de mexer) — atualizado junto. Revalidado
contra os p-valores já calculados na entrada anterior antes de seguir
pro frontend: bateram exatamente (Cáceres dias chuvosos p=0,0102,
veranico p=0,0049).

**Frontend** — `renderizarDestaqueTendencia(elementoId, t, unidade, rotulos)`,
uma função só reaproveitada nos 3 gráficos de evolução (veranico, dias
chuvosos, intensidade), decide entre 3 textos possíveis a partir de
`significativo`+`direcao`:
1. Significativo (aumento OU redução): nomeia a direção + slope + p-valor,
   cor correspondente (mesma paleta do card de tendência do total anual —
   azul/vermelho/cinza).
2. Não significativo, indicador onde "estável" é a leitura natural
   (intensidade): "Estável — sem tendência estatisticamente
   significativa (p=X)".
3. Não significativo, indicador onde a direção observada ainda merece
   ser nomeada sem prometer significância (dias chuvosos): "Tendência
   de redução, NÃO estatisticamente significativa (p=X)".

**Testado nos 3 municípios contra o texto REAL que cada painel vai
mostrar** (réplica fiel da função extraída do arquivo, rodada contra o
endpoint ao vivo, não só o cálculo isolado):

- Veranico — os 3 municípios caem no caso 1 (significativo, aumento):
  "Tendência de aumento estatisticamente significativa: +0,265
  dias/ano (Mann-Kendall, p=0,003)" (Tangará), análogo em Cáceres
  (p=0,005) e Cuiabá (p=0,013).
- Dias chuvosos — Tangará e Cáceres caem no caso 1 (significativo,
  redução); Cuiabá cai no caso 3: "Tendência de redução, NÃO
  estatisticamente significativa (p=0,083)" — nem esconde a direção
  observada, nem finge significância que não existe.
- Intensidade — os 3 caem no caso 2: "Estável — sem tendência
  estatisticamente significativa (p=0,475)" (Cáceres) e equivalentes.

`manage.py check` limpo, JS revalidado com `node --check`.

**Contexto:** a entrada anterior mostrou intensidade sem tendência
significativa nos 3 municípios, e só uma observação visual (não
testada) de que o veranico máximo parecia crescer em Cáceres. Rodado
agora, sem mudança de código — só `mi._tendencia_de_serie` (já
genérico desde a entrada anterior) aplicado às séries de
`veranico_maximo_serie_anual` e `dias_chuvosos_serie_anual` dos 3
municípios piloto.

**Veranico máximo anual — significativo nos 3, sem exceção:**
Tangará da Serra (slope +0,265 dias/ano, p=0,0034), Cáceres (+0,278,
p=0,0049), Cuiabá (+0,444, p=0,0133). Magnitude grande: os três
praticamente dobraram o veranico máximo típico entre os 5 primeiros e
os 5 últimos anos da série (ex.: Cáceres 22,8→44,8 dias).

**Dias chuvosos anuais — significativo em 2 dos 3:** Tangará
(slope −0,400 dias/ano, p=0,0268) e Cáceres (−0,400, p=0,0102)
confirmam formalmente a queda já vista por comparação de médias;
Cuiabá fica no limite (p=0,083, não significativo a 5%).

**Quadro consolidado dos 4 testes** (total anual, dias chuvosos,
intensidade, veranico máximo):

| | Tangará | Cáceres | Cuiabá |
|---|---|---|---|
| Total anual ↓ | não sig. (p=0,107) | **sig.** (p=0,011) | não sig. (p=0,059) |
| Dias chuvosos ↓ | **sig.** (p=0,027) | **sig.** (p=0,010) | não sig. (p=0,083) |
| Intensidade | estável (p=0,922) | estável (p=0,475) | estável (p=0,291) |
| Veranico máximo ↑ | **sig.** (p=0,0034) | **sig.** (p=0,0049) | **sig.** (p=0,0133) |

**Leitura**: Cáceres é o único caso 4/4 completo isoladamente. Mas o
achado mais forte da análise inteira é justamente o que menos se
esperava de antemão — **veranico máximo é o único indicador
significativo nos 3 municípios sem exceção**, mais robusto até que a
queda do total anual (que só Cáceres confirma com rigor estatístico).
A narrativa defensável com o dado atual: o sinal mais sólido de
mudança no regime pluviométrico de MT não é "chove menos no total",
é "os períodos secos estão ficando mais longos" — presente e
significativo nos 3 casos testados.

**Não implementado nesta entrada** (pedido explícito do usuário — só
os testes, sem mexer em frontend/endpoint): esses p-valores não estão
expostos na home ainda; os gráficos de evolução já mostram as séries
brutas (veranico, dias chuvosos), só não com o resultado do teste de
significância ao lado. Registrado como possível próximo passo.

## 2026-09-01 — Evolução temporal (45 anos) dos indicadores de FASE 2 + achado: sem intensificação significativa em MT (nos 3 municípios testados)

**Contexto:** os cards da FASE 2 (entrada anterior) só mostravam o valor
mais recente. Pedido do usuário: gráfico de evolução ano a ano
(1981→2025) pra dias chuvosos, intensidade e veranico máximo, cada um
atrás de um botão "ver evolução" — mesmo padrão do gráfico do SPI.

**Backend** (`climate/municipio_indicators.py`) — 2 refactors sem
mudança de comportamento (revalidados: `tendencia_mann_kendall` de
Tangará/Cáceres bateu exatamente com os valores já vistos antes do
refactor) + 3 funções novas:
- `_maior_sequencia_em_lista` extraído de `_maior_sequencia_seca` (o
  núcleo do cálculo de veranico, já corrigido na entrada anterior) —
  reaproveitado pela série anual sem duplicar a lógica corrigida.
- `_tendencia_de_serie(anos, valores)` extraído de
  `tendencia_mann_kendall` — Mann-Kendall/Sen's slope agora genérico
  pra qualquer série anual, não só o total de chuva.
- `_registros_diarios_todos_anos(municipio)`: uma query só (todo o
  histórico diário), agrupada em Python por ano civil completo — base
  compartilhada das 3 séries novas (evita 45 queries por indicador).
- `dias_chuvosos_serie_anual`, `intensidade_serie_anual` (inclui a
  tendência **da própria intensidade**, via `_tendencia_de_serie` —
  independente da tendência do total anual), `veranico_maximo_serie_anual`
  (reinicia a contagem em cada 1º de janeiro, mesmo critério calendário
  fechado dos outros indicadores anuais).

**Endpoint novo**: `GET /api/municipios/<id>/series-anuais/` — as 3
séries juntas (compartilham a query base), buscado **sob demanda**
(só no 1º clique em "ver evolução", mesmo padrão lazy do `spi-serie/`)
— não entra no payload inicial de `indicadores-fase2/`. Testado com
Adamantina/SP (sem CHIRPS): HTTP 200, tudo `null`.

**Frontend**: 4 botões "ver evolução" na seção FASE 2 — Dias Chuvosos
(barras, alterna limiar 1/5/10mm sem nova requisição — os 3 já vêm na
mesma resposta), Intensidade (linha + reta de Sen's slope tracejada
sobreposta, mesmo estilo do gráfico de tendência anual), Dias Secos
Consecutivos (barras do máximo por ano), e um 4º gráfico — **sugestão
aprovada pelo usuário**, "Ver assinatura: Frequência × Intensidade":
eixo duplo (Chart.js nativo, sem lib nova) combinando as duas séries
já buscadas num gráfico só, revelando se o padrão é "chove menos vezes
porém mais forte" ou o oposto. As 4 séries são buscadas uma vez só
(cache client-side) e reaproveitadas por todos os botões, inclusive o
combinado.

**ACHADO — testado nos 3 municípios, não confirma a hipótese de
intensificação**: nenhum dos três (Tangará da Serra, Cáceres, Cuiabá)
mostrou tendência de intensidade estatisticamente significativa, em
nenhuma direção:

| Município | Slope intensidade (mm/dia-chuvoso/ano) | p-valor | Significativo? |
|---|---|---|---|
| Tangará da Serra | +0,0010 | 0,922 | Não |
| Cáceres | −0,0054 | 0,475 | Não |
| Cuiabá | −0,0125 | 0,291 | Não |

Ou seja: em nenhum dos três a chuva está ficando mais intensa por
evento (nem menos, de forma estatisticamente robusta) — os slopes são
praticamente nulos. O que os dados MOSTRAM (com a mesma consistência
já vista no total anual) é queda na **frequência**: dias chuvosos
caindo em todos os três (Cáceres: média de 176/ano nos 5 primeiros
anos → 152/ano nos 5 últimos; padrão parecido em Tangará e Cuiabá — já
registrado na entrada FASE 1/tendência anterior). A leitura defensável
com o dado atual é "menos dias de chuva explicam a queda do total, não
intensificação dos eventos individuais" — o oposto da hipótese de
"chove menos vezes mas mais forte" que motivou o gráfico combinado. Um
achado real e honesto, ainda que diferente do esperado — registrado
aqui em vez de forçar uma narrativa que o dado não sustenta.

**Achado secundário, não testado formalmente**: o veranico máximo por
ano de Cáceres mostra um padrão visual crescente nos anos recentes
(16-27 dias nos primeiros 5 anos da série vs. 32-66 dias nos últimos
5) — mas isso é uma observação visual da série bruta, **sem teste de
significância aplicado** (Mann-Kendall não foi rodado pra veranico
nesta entrada, só pra total anual e intensidade). Vale investigar
formalmente numa entrada futura se for do interesse da dissertação.

## 2026-08-31 (continuação 5) — FASE 2 dos indicadores por município: veranico, dias chuvosos, intensidade, recordes, tendência (Mann-Kendall + Sen's slope)

**Contexto:** FASE 1 (SPI, climatologia, anomalia, percentil, acumulados
— entradas anteriores) validada. FASE 2 adiciona os indicadores que
faltavam do pedido original: veranico, dias chuvosos, intensidade da
chuva, recordes históricos, e tendência de longo prazo — agora com
Mann-Kendall + Sen's slope em vez da regressão linear simples
(`climate.trends.tendencia_anual`, que **continua existindo**, não foi
removida nem alterada).

**Refactor prévio em `climate/trends.py`** (pra recordes não duplicar
query): `normais_climatologicas_mensais` agregava totais por mês
individual e SÓ DEPOIS agrupava por mês do calendário — extraí a
primeira parte pra uma função nova e pública, `totais_mensais(municipio)`
(dict `{date: total_mm}`, um por mês da série toda), que
`normais_climatologicas_mensais` agora consome. Zero mudança de
comportamento (validado: `climatologia_mensal` de Tangará bateu
exatamente com o valor já visto na entrada da FASE 1 antes do
refactor) — só reuso.

**5 funções novas em `climate/municipio_indicators.py`** (mesmo padrão
da FASE 1: por município, on-the-fly, cache Redis, `None` nunca
cacheado):
- `veranico(municipio)` — maior sequência de dias com chuva < 1mm,
  recente (12 meses) e recorde histórico. Descrito de forma neutra
  ("dias secos consecutivos"), sem linguagem agronômica prescritiva —
  decisão explícita do usuário.
- `dias_chuvosos(municipio, ano=None)` — contagem nos limiares 1/5/10mm,
  ano civil completo mais recente por padrão.
- `intensidade_chuva(municipio, ano=None)` — total do ano ÷ dias com
  chuva >1mm (concentrada vs. distribuída).
- `recordes(municipio)` — ano/mês mais chuvoso e mais seco já
  registrados, via `trends.totais_anuais`/`trends.totais_mensais`
  (só encontra o extremo, nenhum cálculo novo).
- `tendencia_mann_kendall(municipio)` — ver fórmulas e validação
  abaixo.

**Bug real encontrado e corrigido durante o teste** (não só "rodou sem
erro"): `_maior_sequencia_seca` devolvia `inicio: None` sempre, com
`fim` correto. Causa: a condição de continuação da sequência checava
só se a DATA era consecutiva à anterior, não se o DIA ANTERIOR também
era seco — um dia seco logo depois de um dia de chuva contava como
"continuação" de uma sequência que não existia. Corrigido rastreando
`dia_anterior_seco` junto com a contiguidade de data; revalidado com 2
casos controlados (sequência simples e sequência com buraco de dado no
meio, que não deve encadear através do buraco) antes de rodar em dado
real de novo.

**Mann-Kendall + Sen's slope** (`climate/municipio_indicators.py`,
funções privadas `_mann_kendall_s_z_p`/`_sens_slope`) — zero
dependência nova, nem numpy: `S = Σsign(x_j-x_i)` (todo par i<j),
`Var(S)` com correção de empates, `Z` com correção de continuidade,
`p = math.erfc(|Z|/√2)` (stdlib resolve a CDF da normal padrão sem
precisar de `scipy.stats.norm`). Sen's slope = mediana das inclinações
par a par (Theil-Sen), intercepto = `mediana(y) - slope×mediana(x)`.
Ver docs/DECISOES.md pra fórmulas completas e a validação com série
sintética.

**Endpoint novo**: `GET /api/municipios/<id>/indicadores-fase2/`
(`api/views.py`/`api/urls.py`, mesmo padrão `JsonResponse` dos outros
5 endpoints do app). Testado com Adamantina/SP (sem CHIRPS): HTTP 200,
tudo `null`.

**Frontend**: nova subseção "📊 Análise Climática Avançada" abaixo da
seção FASE 1 em `core/templates/core/index.html` — cards de veranico
(2), dias chuvosos, intensidade, recordes (ano/mês); destaque colorido
da tendência (vermelho = redução significativa, azul = aumento
significativo, cinza = sem significância — mesma lógica de cor
"condição a destacar" já usada no SPI); gráfico de linha dos totais
anuais com a reta de Sen's slope sobreposta (2º dataset tracejado,
Chart.js). Buscado em paralelo ao resto ao selecionar cidade.

**Validação da tendência**: série sintética com slope conhecido
(1.0/-1.8mm/ano sem ruído) recuperou o slope EXATO; com ruído
moderado, recuperou próximo do valor real e manteve significância.
Contra dado real, cross-validado com a regressão linear simples que já
existia (`tendencia_anual`) — concordância próxima em ambos os
municípios pilotos: Tangará -3,11 mm/ano (Sen) vs. -3,50 (OLS),
Cáceres -4,02 (Sen) vs. -3,99 (OLS). Mann-Kendall aí acrescenta
nuance que a regressão simples não dá: Cáceres tem tendência de
redução estatisticamente **significativa** (p=0,011), Tangará **não**
(p=0,107) apesar de um slope de magnitude parecida — a série de
Tangará tem mais ruído ano a ano, então a mesma inclinação não passa
no teste de significância. Comparação com a média bruta dos 5
primeiros vs. 5 últimos anos confirma a mesma direção de queda nos
dois municípios.

## 2026-08-31 (continuação 4) — Modo "Todas as escalas" no gráfico de evolução do SPI

**Contexto:** o gráfico de evolução (entrada anterior) só mostrava uma
escala de SPI por vez. O usuário pediu um modo comparativo — as 4
escalas sobrepostas revelam a dinâmica de uma seca se espalhando (SPI-1
cai antes do SPI-12, sinal de que o déficit de curto prazo ainda não
"contaminou" o longo prazo), leitura que a banca da dissertação valoriza.

**Só `core/templates/core/index.html`** — nenhuma mudança de backend
(o endpoint `spi-serie` já aceitava uma escala por chamada; o modo
"Todas" só passou a chamá-lo 4 vezes, reaproveitando o cache por
escala que já existia).

- Botão "Todas" no mesmo grupo dos 4 botões de escala.
  `carregarEDesenharSpiEvolucao` busca em paralelo (`Promise.all`) só
  as escalas ainda não cacheadas — trocar entre "SPI-3" e "Todas" não
  rebusca o que já foi visto.
- 4 linhas, cores da paleta Okabe-Ito (segura pra daltonismo),
  escolhidas pra não colidir com as faixas de fundo azul/vermelho do
  modo individual: SPI-1 laranja `#E69F00`, SPI-3 verde-azulado
  `#009E73`, SPI-6 roxo-avermelhado `#CC79A7`, SPI-12 cinza-escuro
  `#343a40`. Linhas mais finas (`borderWidth: 1.5` vs. `2` no modo
  individual) pra não virar borrão.
- Legenda (Chart.js) só aparece no modo "Todas" — no modo de escala
  única continua desligada (uma linha não precisa de legenda).
- **Faixas de fundo REMOVIDAS no modo "Todas"** (decisão confirmada
  com o usuário antes de codar, não só "mais discretas") — com 4
  linhas sobrepostas cruzando ±1 em momentos diferentes, a faixa vira
  ruído; o valor do modo comparativo é a defasagem ENTRE escalas, não
  a reclassificação contra o limiar. O modo de escala única manteve as
  faixas exatamente como estavam.
- Eixo X é a união ordenada das datas das 4 séries (não só a da
  primeira escala) — protege contra desalinhamento se uma escala
  tiver histórico disponível mais curto que outra (`spanGaps: true`
  nos datasets, `null` nos pontos sem dado daquela escala naquela
  data).
- Botões de período (5/10/Tudo) continuam funcionando igual, refiltrando
  as 4 séries em cache sem nova requisição.

**Testado**: simulei a lógica de união/alinhamento em Node contra os 4
endpoints reais (Tangará, período padrão de 10 anos) — 119 rótulos de
mês no eixo X, **as 4 escalas com 119 pontos não-nulos cada, zero
lacuna** no período padrão (SPI-12 já tem histórico suficiente bem
antes de 2016, então nenhuma escala fica "atrasada" nesse recorte).
`manage.py check` limpo, bloco `<script>` revalidado com `node --check`.

## 2026-08-31 (continuação 3) — Dois ajustes na seção de indicadores: anomalia mais clara + gráfico de evolução do SPI

**Ajuste 1 — anomalia percentual enganosa em mês seco.** O card de
anomalia (entrada anterior) destacava só o percentual (ex.: "101% da
média"). Em mês seco (jul/MT, média histórica ~12,9 mm), um percentual
perto de 100% de um valor quase nulo passa impressão de normalidade
que o número absoluto (+0,1 mm) desmente. Correção só em
`core/templates/core/index.html` (frontend, `anomalia_mensal` já
devolvia todos os campos usados): absoluto e percentual agora lado a
lado, mesmo peso visual (`.anomalia-dupla`), e nota discreta em itálico
quando `media_historica_mm < 30` ("valores baixos típicos do período
seco — variação percentual pouco representativa").

**Ajuste 2 — gráfico de evolução do SPI.** Endpoint novo
`GET /api/municipios/<id>/spi-serie/?escala=N` (`api/views.py`/
`api/urls.py`, mesmo padrão `JsonResponse` dos outros 4 endpoints do
app — `escala` fora de `(1,3,6,12)` devolve 400) repassa
`municipio_indicators.spi_serie` sem recalcular nada; filtro de
período (5/10 anos/tudo) fica no frontend por decisão explícita — a
série inteira (≤ ~545 pontos mensais) já é pequena e já vem cacheada,
recortar um array não justificava lógica nova no backend.

Botão "Ver evolução do SPI" abaixo dos 4 cards, painel escondido por
padrão (`display: none`) até o clique. Dentro: botões de escala
(1/3/6/12, padrão SPI-3) e período (5/10/tudo, padrão 10 anos — troca
de período só refiltra o array já em cache, sem nova requisição; troca
de escala busca sob demanda e cacheia por escala, resetado a cada
município novo escolhido). Gráfico de linha (Chart.js, já usado) com
faixas de fundo — seca (SPI < -1) e úmido (SPI > +1) — desenhadas por
um plugin Chart.js **inline** (`beforeDatasetsDraw`, ~15 linhas) em vez
de trazer `chartjs-plugin-annotation` como dependência nova; zona
normal (-1 a 1) fica sem preenchimento. Opacidade das faixas bem baixa
(`rgba(..., 0.06)`) a pedido explícito do usuário — são só contexto de
leitura, a linha do SPI é a protagonista. Eixo X usa rótulos
categóricos (string "mmm/aaaa"), não escala de tempo — evita precisar
do adaptador de datas do Chart.js (mais uma dependência).

Nenhuma mudança em `climate/municipio_indicators.py`, painel privado,
ou Windy. `manage.py check` limpo; endpoint novo testado via `curl`
(Tangará/SPI-3: 545 pontos, 1981-03 a 2026-07; escala inválida → 400);
bloco `<script>` revalidado com `node --check` depois das duas
mudanças.

## 2026-08-31 (continuação 2) — Indicadores climáticos (FASE 1) na home pública

**Contexto:** primeira etapa da home nova — mostrar os indicadores de
`climate/municipio_indicators.py` (entrada anterior) pro município
escolhido no seletor Estado/Cidade que já existia, sem exigir
fazenda/estação cadastrada.

**Backend** — `api/views.py`/`api/urls.py`, novo endpoint
`GET /api/municipios/<id>/indicadores/`, mesmo padrão dos 3 endpoints
vizinhos já existentes nesse app (`JsonResponse` simples — `api/` nunca
usou DRF apesar de instalado; decisão confirmada com o usuário via
pergunta direta antes de codar, pra não introduzir um padrão novo só
pra este endpoint). Só chama as funções de `municipio_indicators.py` e
serializa — nenhum cálculo novo. Município sem CHIRPS suficiente (fora
de MT hoje) devolve HTTP 200 com todos os campos `null`/vazios, nunca
500 — testado com Adamantina/SP de propósito.

**Frontend** — só `core/templates/core/index.html` (HTML+CSS+JS,
template monolítico, mesmo padrão do resto do arquivo): nova seção
"Indicadores Climáticos Históricos" entre "Previsão de 7 Dias" e o
iframe do Windy — separa clima agora/previsão (Open-Meteo) de clima
histórico (CHIRPS) antes do radar em tempo real. Disparada de dentro
de `aplicarSelecaoMunicipio()` (mesmo hook que já carregava o clima
Open-Meteo ao escolher cidade), sem tocar na mecânica existente.

- **4 cards de SPI** (1/3/6/12, as quatro — não só 3/6, pedido
  explícito do usuário), rótulo curto do horizonte de cada escala
  ("SPI-1 · último mês" ... "SPI-12 · ano"). Cor por CLASSIFICAÇÃO,
  não por escala — escala simétrica de verdade: verde só pra `normal`,
  amarelo→laranja→vermelho conforme a seca piora, azul claro→escuro
  conforme o excesso de chuva aumenta. Excesso de chuva NÃO usa verde
  (ajuste pedido depois do plano inicial — tratar excesso como "bom"
  esconderia uma condição que também merece destaque).
- Cards de anomalia mensal e percentil histórico (frase "Nº mais seco
  desde ANO" montada no frontend a partir dos campos que o endpoint já
  devolve prontos).
- Gráfico de barras da climatologia mensal (Chart.js 4.4.4 via CDN —
  mesma versão já usada em `dashboard/painel.html`, Etapa 8.1, sem
  dependência nova).
- Cards de acumulados 7/30/90 dias, "aguardando dado" quando `null`
  (caso atual das janelas de 7/30 dias, CHIRPS parado em 2026-07-31 —
  lag normal de publicação, já diagnosticado na entrada anterior).
- Município sem CHIRPS: um aviso único substitui a seção inteira, sem
  tentar desenhar 4 cards vazios e um gráfico sem dado.

Windy/Open-Meteo não foram tocados — seção CHIRPS só foi adicionada.
Nada em `dashboard/`, `farms/` ou painel privado mudou.

**Testado**: `manage.py check` limpo; endpoint testado via `curl` com 3
municípios reais (Tangará da Serra, Cáceres, Cuiabá — JSON completo,
todos os campos populados) e 1 sem CHIRPS (Adamantina/SP — HTTP 200,
tudo `null`, sem erro); bloco `<script>` extraído do template e
validado com `node --check` (sintaxe JS limpa) — sem navegador
disponível nesta sessão pra clique-a-clique visual completo.

## 2026-08-31 (continuação) — Indicadores climáticos por município (climate/municipio_indicators.py)

**Contexto:** investigação prévia (pedida antes de codar) mostrou que
`spi.services.calcular_serie_spi` já calculava por MUNICÍPIO desde a
Etapa 7.1 — só a gravação em `SpiResult` amarrava a estação. Com o
CHIRPS dos 142 municípios de MT já importado, deu pra expor esse
cálculo (e o de `climate/trends.py`, que já era por-município) num
módulo novo, reaproveitável tanto pela home pública (município
clicado no mapa, sem fazenda) quanto pelo painel privado no futuro.

**O que foi feito** — `climate/municipio_indicators.py` (novo), 6
funções públicas, todas recebendo `municipio` (objeto ou
`codigo_ibge`), zero model/migration:
- `spi_serie`/`spi_atual` (SPI-1/3/6/12) — repassa pra
  `spi.services.calcular_serie_spi`. SPI-1 exigiu adicionar `1` a
  `spi/services.py:ESCALAS_VALIDAS` (cálculo já suportava, só a
  validação bloqueava) — não mexe em `SpiResult` nem em
  `calcular_spi`, que continuam só 3/6/12.
- `climatologia_mensal` — repassa pra
  `climate.trends.normais_climatologicas_mensais`.
- `anomalia_mensal` — nova: chuva do mês vs. média histórica do mesmo
  mês do calendário (ano avaliado excluído da própria média).
- `percentil_historico_mensal` — nova: onde a chuva do mês se
  posiciona no histórico (percentil 0-100 + posição ordinal "Nº mais
  seco/chuvoso desde ANO").
- `acumulados_municipio` — nova: 7/30/90 dias, só CHIRPS (sem misturar
  com dado local de fazenda — isso continua em
  `dashboard.services.acumulados`, não tocado).
- Cache Redis opcional (`CACHE_HABILITADO`, flag de módulo fácil de
  desligar), TTL 1 dia, resultado `None` nunca cacheado.

**Testado**: 3 municípios (Tangará da Serra, Cáceres, Cuiabá) × 6
funções, primeiro sem cache (valor cru conferido), depois com cache
(hit confirmado fisicamente no Redis, 20ms → <1ms, resultado
idêntico). Achado à parte, não é bug: `acumulados_municipio` retornou
`chirps_mm: None` pras janelas de 7 e 30 dias nos 3 municípios — o
CHIRPS mais recente no banco é 2026-07-31, e hoje é 2026-08-31 (mês
inteiro sem cobertura ainda, publicação do CHIRPS tem defasagem
própria); a janela de 90 dias já alcança dado real e voltou valor
normal nos 3 casos. Detalhe completo da decisão de arquitetura em
docs/DECISOES.md.

**Pendente, registrado a pedido do usuário**: FASE 2 (veranicos, dias
chuvosos, intensidade da chuva, recordes, tendência de longo prazo)
fica pra depois da validação da FASE 1. Já decidido pra quando chegar:
a tendência de longo prazo vai usar **Mann-Kendall + Sen's slope**
(testa significância estatística, padrão pra séries climáticas) em
vez da regressão linear simples que `climate/trends.py:tendencia_anual`
usa hoje — `tendencia_anual` não foi alterado nesta entrada.

## 2026-08-31 — Rebranding visível: "GeoClima MT" → "MonitorChuva MT"

**Contexto:** pedido explícito do usuário — trocar só o nome que o
usuário FINAL vê na tela (título de aba, navbar, rodapé, e-mails),
sem tocar em nada interno (containers `geoclima_web`/`geoclima_db`,
nome do projeto Django `geoclima`, banco, variáveis de ambiente,
domínio, nomes de apps/models/arquivos `.py`).

**O que foi feito:** troca de texto em 22 templates — os dois layouts
base (`templates/base.html`, usado pelas páginas de auth/painel, e
`core/templates/core/index.html`, a Home pública, que não estende
`base.html`) tiveram `<title>`, navbar-brand (emoji 🌍 → 🌧️) e rodapé
(`© 2026 ...`) trocados; os outros 20 templates só tinham
`{% block title %}... — GeoClima MT{% endblock %}`, trocado em massa.
Também `core/templates/core/ajuda.html` (H1 da página), 3 ocorrências
em `farms/templates/farms/relatorio_fazenda.html` (`<title>`,
subtítulo do cabeçalho, rodapé do relatório impresso) e os textos dos
e-mails de recuperação de senha (`accounts/templates/accounts/
password_reset_email.html`, `password_reset_subject.txt`).

**Subtítulo novo** ("Monitoramento de precipitação e índice de seca
em Mato Grosso") só entrou na Home — único lugar com navbar espaçosa o
bastante pra caber uma segunda linha sem forçar; as páginas que usam
`base.html` mantiveram a navbar de uma linha só, sem subtítulo, pra
não repetir a mesma frase em toda página do painel.

**O que NÃO foi tocado** (deliberado, confirmado depois via `grep
-r "GeoClima"`): containers Docker, `settings.py` (só tinha um
comentário interno citando "GeoClima MT", não texto exibido),
`Dockerfile`, e os arquivos de documentação (`README.md`, `CLAUDE.md`,
`docs/*.md`, `requisitos/requisitos.md`) — não são tela vista pelo
usuário final do sistema, e `docs/RELATORIO_TECNICO.md` em particular
documenta o histórico real do projeto sob o nome que ele tinha à
época, não faz sentido reescrever retroativamente.

**Testado**: `manage.py check` limpo, HTML renderizado via `curl` na
Home (navbar com subtítulo) e no login (`base.html`, título/navbar/
rodapé), `grep -r "🌍"` e `grep -r "GeoClima"` no repo confirmando
zero ocorrência em template/e-mail — só sobrou em documentação.

## 2026-08-23 (continuação 22) — Cache do Django trocado pra Redis (produção roda 3 workers do Gunicorn)

**Contexto:** antes de subir a entrada anterior (pipeline climático
completo) pro GitHub, o usuário pediu pra confirmar onde `CACHES`
apontava em `geoclima/settings.py`. Confirmado: nenhuma configuração
— Django caindo no padrão, `LocMemCache`. O usuário revelou um dado
novo, que eu não tinha ao escrever a entrada anterior: **a produção
real roda 3 workers do Gunicorn**, não o `runserver` único que o
`docker-compose.yml` do repositório usa em dev. Com `LocMemCache`
(por processo), a guarda de debounce da entrada anterior não
protegeria nada entre os 3 workers — exatamente a limitação já
documentada como risco futuro, só que já era o presente.

**O que foi feito:**

- **`geoclima/settings.py`**: `CACHES` configurado com o backend Redis
  **nativo** do Django (`django.core.cache.backends.redis.RedisCache`,
  disponível desde o Django 4.0) — zero lib nova, usa o pacote `redis`
  que já é dependência do projeto (Celery). Aponta pra
  `CACHE_REDIS_URL` (nova variável de ambiente), banco Redis **1**
  (separado do banco 0, que o Celery já usa).
- **`docker-compose.yml`**: `CACHE_REDIS_URL=redis://redis:6379/1`
  adicionado só ao serviço `web` (único que cria `Station` e roda a
  guarda) — `celery_worker`/`celery_beat` não precisam.

**Testado com prova direta (não só "a configuração parece certa"):**
- Backend confirmado via `type(caches['default'])`.
- Chave gravada conferida fisicamente dentro do Redis via `redis-cli
  -n 1 KEYS`.
- **Teste decisivo**: `cache.add()` da mesma chave em duas chamadas
  `manage.py shell` genuinamente separadas (dois processos distintos,
  simulando o isolamento real entre workers do Gunicorn) — processo A
  grava, processo B vê o lock e é bloqueado. Esse teste "falhava" com
  `LocMemCache` (documentado na entrada anterior); com Redis, passa.
- Pipeline completo (cadastro real via navegador → chain de 3 etapas)
  re-testado do zero: resposta em 613ms, 3 etapas em ordem com
  sucesso, dado real do usuário conferido intacto.

**Detalhe operacional registrado:** variável de ambiente nova no
`docker-compose.yml` só é aplicada com `docker compose up -d web`
(recria o container) — `docker compose restart web` não é
suficiente, mantém as variáveis com que o container foi criado
originalmente.

**Atualizado:** `docs/DECISOES.md` (nova entrada fechando a limitação
que a entrada anterior tinha deixado em aberto).

---

## 2026-08-23 (continuação 21) — Pipeline climático completo automático (SPI → cenários → alertas)

**Contexto:** extensão do que a entrada anterior implementou (só
`calcular_spi` automático). Faltava encadear `gerar_projecoes` e
`detectar_alertas_climaticos` na mesma automação, na ordem certa —
alertas leem o SPI mais recente, então rodar fora de ordem geraria
alerta desatualizado ou vazio.

**Investigação feita antes de codar (pedido explícito, aprovada antes
da implementação):**
- `gerar_projecoes`: só aceita `--meses`, **sem `--municipio`** — roda
  sempre pra todos os municípios `ativo=True` de uma vez.
- `detectar_alertas_climaticos`: **sem nenhum argumento**, `100%
  global` — `spi/alert_checks.py:_mais_recente_por_estacao` filtra só
  por `scale`, nunca por município, varre `SpiResult` da base inteira.
- Tempo medido de verdade (não estimado), contra o banco atual:
  `gerar_projecoes` **7,2s**, `detectar_alertas_climaticos` **3,9s** —
  somados ao `calcular_spi` (24-66s), o pipeline inteiro chega a
  **~77s**.
- Guard de idempotência do signal anterior: **confirmado que não
  existia**. Ficou mais grave com este pedido, porque agora cada
  disparo custa até ~77s (não só ~24-66s), e o caminho do Shapefile
  (`farms/views.py:_criar_estacoes_do_shapefile`) já cria várias
  estações numa única requisição — sem guard, N pontos = N pipelines
  completos e redundantes ao mesmo tempo pro mesmo município.

**O que foi feito:**

- **`spi/tasks.py`**: nova task `detectar_alertas_climaticos_task`
  (só `call_command("detectar_alertas_climaticos")`), ao lado da
  `calcular_spi_municipio` já existente.
- **`climate/tasks.py`**: nova task `gerar_projecoes_task` (só
  `call_command("gerar_projecoes")`) — mora aqui, não em `spi/`,
  porque é o command do app `climate`.
- **`stations/signals.py`** (reescrito): em vez de disparar
  `calcular_spi_municipio.delay()` direto, monta uma **Celery chain**
  (`calcular_spi_municipio.si() | gerar_projecoes_task.si() |
  detectar_alertas_climaticos_task.si()`) — a ordem é garantida pelo
  próprio Celery (uma etapa só roda se a anterior terminou), retry
  independente por etapa. Ganhou também uma **guarda de debounce**
  (`django.core.cache.cache.add()`, TTL de 120s, chave por
  `codigo_ibge`): se já existe uma chain recém-disparada pro mesmo
  município, não dispara outra.

**Decisão registrada em DECISOES.md:** Celery chain (Opção B), não uma
task só com 3 `call_command` em sequência — decisão do usuário, com o
raciocínio completo lá.

**Nenhuma migration** — chain, tasks e guard de cache não tocam model
nenhum.

**Testado com execução real (não simulada):**
- Chain completa disparada por 2 estações criadas na mesma fazenda:
  só **1** `calcular_spi_municipio` recebido pelo worker (debounce
  bloqueou a segunda) — as 3 etapas rodaram em ordem
  (calcular_spi 47s → gerar_projecoes 0,8s → detectar_alertas 1,3s),
  todas com sucesso, e **ambas** as estações ficaram com SPI (1.623
  registros cada) e Projection (18 registros cada) — a chain recalcula
  pra todas as estações do município, não só a que disparou.
- Cadastro via formulário real no navegador (Playwright): **539ms** de
  resposta — o pipeline de ~1 minuto roda inteiro em background.
- **Achado durante o teste, explicado (não é bug):** testar o
  debounce via `manage.py shell -c "..."` em duas chamadas separadas
  mostrou uma segunda chain disparando — porque cada chamada de
  `manage.py shell` é um **processo Python separado**, com sua própria
  instância de `LocMemCache` (o backend padrão do Django, sem
  configuração própria neste projeto). Refeito o teste do jeito que
  reflete o uso real (duas estações cadastradas via **navegador**, ou
  seja, duas requisições HTTP tratadas pelo **mesmo processo
  `runserver`**): confirmado **1 único** disparo pras duas. A guarda
  funciona pro caso que importa (usuário cadastrando estações pela
  interface); só não é compartilhada entre processos `manage.py
  shell` isolados, o que nunca acontece em uso real.
- Estação num município `ativo=False`: comportamento preservado (já
  testado na entrada anterior, não re-testado aqui).
- Dados de teste removidos depois, filtrados por owner; as duas
  fazendas reais do `daniel` conferidas intactas antes e depois.

**Melhoria de UX registrada como pendência (pedido explícito, não
implementada nesta tarefa):** hoje o dashboard mostra a mesma
mensagem ("Ainda não há SPI suficiente...") tanto para "município sem
CHIRPS habilitado" quanto para "SPI está sendo calculado agora, volte
em instantes" — são situações diferentes (uma é permanente, a outra é
temporária) que deveriam ter mensagens diferentes. Não implementado
aqui — precisaria de alguma forma de saber que existe uma chain em
andamento pra aquele município (ex.: reaproveitar a própria chave de
debounce do cache pra decidir a mensagem, ou checar o estado da task
via `AsyncResult`) — fica pra uma próxima tarefa com esse escopo
específico.

**Atualizado:** `docs/DECISOES.md` (raciocínio completo Opção A vs B,
critério do TTL de debounce, limitação do LocMemCache por processo).

---

## 2026-08-23 (continuação 20) — Cálculo automático de SPI ao cadastrar estação nova

**Contexto:** pedido do usuário — hoje, uma fazenda/estação nova num
município já com CHIRPS importado não tinha SPI calculado até alguém
rodar `calcular_spi` manualmente, e o dashboard mostrava "Ainda não há
SPI suficiente". Não escala pra demonstração com múltiplos usuários
cadastrando fazendas.

**Investigação feita antes de codar (pedido explícito do usuário,
aprovada antes da implementação):**
- Duas rotas criam `Station` hoje: `stations/views.py:criar_estacao`
  (cadastro normal) e `farms/views.py:_criar_estacoes_do_shapefile`
  (pontos de um Shapefile). Um signal cobre as duas sem duplicar
  chamada em cada view.
- `calcular_spi` faz duas coisas: `spi.services.calcular_serie_spi`
  (cálculo puro, por município) + um loop de `update_or_create` por
  estação. Medido nesta sessão: **~24-66s** pra recalcular um
  município com histórico de 45 anos (tempo cresce com o número de
  estações do município, não só a nova).
- Não existia nenhum signal em `Station`/`Farm` — o único precedente
  no projeto é `accounts/signals.py` (cria `Profile` ao criar `User`),
  usado como modelo de implementação.

**O que foi feito:**

- **`stations/signals.py`** (novo): `post_save` em `Station`. Se
  `created=True` e `estacao.farm.municipio.ativo` (mesmo sinal já
  usado em todo o projeto pra "tem CHIRPS suficiente" — nenhum
  critério novo inventado), despacha
  `spi.tasks.calcular_spi_municipio.delay(codigo_ibge)`.
- **`stations/apps.py`**: `ready()` importando `stations.signals`,
  mesmo padrão de `accounts/apps.py`.
- **`spi/tasks.py`** (novo): task Celery `calcular_spi_municipio` —
  **não** reimplementa nada, só chama
  `call_command("calcular_spi", municipio=codigo_ibge)`, mesmo padrão
  já usado por `climate/tasks.py:atualizar_chirps` com `import_chirps`.
  Retry declarativo igual à task do CHIRPS.

**Decisão registrada em DECISOES.md:** assíncrono via Celery, não
síncrono na view — decisão com trade-off explícito, ver lá.

**Nenhuma migration** — signal e task Celery não tocam model nenhum.

**Testado (não simulado):**
- Estação criada via `Station.objects.create()` (caminho do
  Shapefile): task disparada, log do worker confirmado, SPI calculado
  em ~66s (4 estações no município nesse momento), `serie_spi()` e
  `gerar_insights()` passaram a devolver dado real pra fazenda de
  teste sem rodar `calcular_spi` manualmente.
- Estação criada num município `ativo=False` (Acrelândia/AC):
  nenhuma task disparada, nenhum erro, cadastro seguiu normal — o
  "não fazer nada" do requisito confirmado.
- Cadastro via formulário real (Playwright, `/painel/estacoes/nova/`):
  resposta HTTP em **719ms** — confirma que o cálculo (~1 minuto) não
  trava o cadastro, roda em background.
- Dados de teste removidos depois, filtrados por
  `owner=joao.produtor`; as duas fazendas reais do `daniel` ("fazenda
  Rocha" e "faz Taruma") conferidas intactas antes e depois.

**Atualizado:** `docs/DECISOES.md` (raciocínio síncrono vs. Celery,
por que signal e não chamada direta na view).

---

## 2026-08-23 (continuação 19) — Rodapé simplificado

**Contexto:** pedido do usuário. O rodapé em `templates/base.html`
(área logada) e `core/templates/core/index.html` (Home pública) tinha
o texto "© 2026 GeoClima MT - Sistema de Inteligência Geográfica e
Monitoramento Climático." em ambos.

**O que foi feito:** removida a segunda parte da frase nos dois
templates — rodapé passa a mostrar só "© 2026 GeoClima MT". Na Home, a
segunda linha do rodapé ("Dados fornecidos por Open-Meteo e
RainViewer.") não foi tocada.

**Testado no navegador via Playwright** em ambos os templates
(`/` e `/ajuda/`, que usa `base.html`): rodapé confirmado com o texto
novo nos dois.

---

## 2026-08-23 (continuação 18) — Removidos os cards "Mapas Agrícolas do Brasil" da Home

**Contexto:** pedido do usuário ao ver print da Home — os 4 cards
"Mapas Agrícolas do Brasil" (Satélite, Previsão de Queimadas, Chuva
Acumulada/CHIRPS, Temperatura) eram `<a href="#">` sem função real
desde a implementação original da Home (nunca chegaram a ser
conectados a nada), já documentados como pendência em
`docs/ARQUITETURA.md`/`docs/ROADMAP.md`.

**O que foi feito:** removido o bloco `<!-- BLOCO: MAPAS AGRÍCOLAS DO
BRASIL -->` inteiro de `core/templates/core/index.html` (título "Mapas
Agrícolas do Brasil", link "Mais mapas", os 4 cards), e o CSS
específico que só esse bloco usava (`.agricultural-map-card` e as
classes filhas `.card-icon`/`.card-title`/`.card-description`/
`.btn-access`/`.badge-info`) — sem deixar CSS morto no arquivo.

**Testado no navegador via Playwright:** seção confirmada ausente do
HTML renderizado, seção de radar (Windy) logo abaixo continua
presente e intacta, nenhum erro de console novo (o único erro
observado é o CORS pré-existente do iframe do Windy, sem relação com
esta mudança).

**Atualizado:** `docs/ARQUITETURA.md` (remoção documentada na seção
`core`), `docs/ROADMAP.md` (item 2.4 atualizado — os cards foram
removidos, não ficaram pendentes), `docs/RELATORIO_TECNICO.md`
(2 menções corrigidas pra refletir a remoção).

---

## 2026-08-23 (continuação 17) — `moderadamente_umido` adicionado a `SpiResult.CLASSIFICATIONS`

**Contexto:** fecha a pendência registrada na entrada anterior. A
refatoração dos Insights corrigiu `classificar_spi()` pra devolver
`moderadamente_umido` (faixa `1.0`–`1.49`, faltante na tabela de
McKee), mas por restrição do pedido não pôde tocar em nenhum model
naquele momento — deixando `classificar_spi()` capaz de devolver um
valor fora do `choices` de `SpiResult.classification`.

**O que foi feito:** `spi.models.SpiResult.CLASSIFICATIONS` ganhou
`('moderadamente_umido', 'Moderadamente Úmido')`, na posição entre
`muito_umido` e `normal` (mesma ordem — do mais úmido pro mais seco —
já usada na lista, e a mesma ordem de `LIMIARES_CLASSIFICACAO` em
`spi/services.py`). Migration `spi/migrations/0002_alter_spiresult_classification.py`
gerada e aplicada — `AlterField` só de metadado `choices` (Django não
grava `choices` como constraint no Postgres por padrão), não altera
nenhuma linha existente na tabela.

**Testado:** `SpiResult(classification='moderadamente_umido').get_classification_display()`
devolve `"Moderadamente Úmido"` corretamente (antes desta migration,
devolveria o valor cru `"moderadamente_umido"`, sem rótulo). Nenhuma
outra alteração — só o model e a migration, conforme pedido.

---

## 2026-08-23 (continuação 16) — Refatoração dos Insights: precisão científica e correção sazonal

**Contexto:** revisão pedida pelo usuário sobre `dashboard/insights.py`
e `spi/services.py:classificar_spi`, com 5 correções específicas. Só
esses dois arquivos (mais este changelog) foram alterados — nenhum
model, migration ou view tocados, por restrição explícita do pedido.

**1. Faixa "moderadamente_umido" faltando.** `LIMIARES_CLASSIFICACAO`
tinha 6 categorias; a tabela padrão McKee et al. (1993) tem 7. Faixa
`1.0`–`1.49` (moderadamente úmido) estava sendo classificada direto
como `muito_umido`. Corrigido — `muito_umido` agora começa em `1.5`,
com `moderadamente_umido` entre `1.0` e `1.5`. `CLASSIFICACOES_UMIDAS`
em `insights.py` atualizado pra incluir o novo valor.

**⚠️ Problema real exposto por essa correção, NÃO resolvido (fora do
escopo autorizado — models não podiam ser tocados):**
`spi.models.SpiResult.CLASSIFICATIONS` só tem 6 opções, sem
`moderadamente_umido`. `classificar_spi()` agora pode devolver um
valor fora desse `choices` — e como Django não valida `choices` no
`.save()` (só em `ModelForm.full_clean()`), o próximo `calcular_spi`
vai gravar `moderadamente_umido` em `SpiResult.classification` sem
erro nenhum, mas fora do que o model declara como válido
(`get_classification_display()` vai devolver o valor cru em vez de um
rótulo bonito pra essas linhas). Precisa de uma migration adicionando
essa choice a `SpiResult.CLASSIFICATIONS` antes do próximo
`calcular_spi` rodar — pendência registrada aqui, não corrigida nesta
tarefa.

**2. "Umidade do solo" removida.** O SPI mede anomalia de
PRECIPITAÇÃO, não umidade do solo — as duas coisas são relacionadas
mas não são a mesma medida (umidade do solo depende também de
evapotranspiração, textura do solo, drenagem, etc., que o SPI não
considera). Toda menção a "solo"/"condição de umidade" trocada por
"precipitação acumulada acima/abaixo/dentro da média histórica".

**3. Frases prescritivas removidas.** O sistema descrevia o SPI E
recomendava ação ("pode ser hora de considerar irrigação", "não é
janela favorável pra plantio", "vale reavaliar reservas de água") —
uma recomendação agronômica que este sistema não tem base pra fazer
(não considera cultura, estágio fenológico, tipo de solo, capacidade
de armazenamento hídrico do produtor, etc.). Reescrito pra só
descrever o estado da anomalia de precipitação, sem prescrever nada.

**4. Contexto sazonal na tendência.** `_insight_tendencia` comparava
SPI-3 bruto sem saber que MT tem uma transição chuvoso→seco
**previsível todo ano** (abril–setembro) — uma queda de SPI nesse
período é o comportamento esperado da estação, não um sinal de
alerta. Corrigido: se a janela de 3 meses cai inteiramente dentro de
abr–set, a queda é contextualizada como sazonal esperada. Fora desse
intervalo (out–mar, estação chuvosa) com queda ≥ 0,5, é sinalizada
como tendência atípica que merece acompanhamento — esse é o caso que
efetivamente merece atenção. Melhora e estável não mudaram de
comportamento (mantidos como estavam, por pedido explícito).

**5. Threshold de tendência documentado.** `±0,3` (nome novo:
`LIMIAR_TENDENCIA`) é limiar empírico deste sistema, sem referência
publicada — comentário corrigido pra dizer isso explicitamente, em vez
de ficar sem explicação nenhuma. **Não foi subido pra ±0,5** apesar da
sugestão no pedido: subir esse valor mudaria também o comportamento de
melhora/estável (compartilham o mesmo cálculo de `variacao`), o que
contradiz o pedido explícito de "manter a tendência de melhora e
estável como estão". Em vez disso, criada uma constante SEPARADA
(`LIMIAR_QUEDA_ATIPICA = 0.5`) só pra decidir se uma queda fora do
período seco é "atípica" — não mexe no limiar geral de piora/melhora.

**Validado com dado real (fazenda "fazenda Rocha", não simulado):**
antes desta correção, o SPI-3 caindo de 1,41 (maio/2026) pra -0,16
(julho/2026) gerava "Tendência de piora... condição ficando mais
seca" — um falso alarme, já que maio-julho é justamente a transição
sazonal esperada em MT. Com a correção 4, a mesma série agora gera
"consistente com a transição sazonal (período seco) — comportamento
esperado pra a época". Confirmado também com dados sintéticos
cobrindo as 3 faixas (seca/normal/úmido) do insight de curto prazo e
os 2 ramos da tendência sazonal (esperada vs. atípica).

**Exemplos — antes e depois (mesmo SPI-3, mensagem diferente):**

| Cenário | Antes | Depois |
|---|---|---|
| Seca (SPI-3 = -1.20) | "Déficit hídrico de curto prazo (SPI-3 = -1.20): solo provavelmente mais seco que o normal pra época. Pode ser hora de considerar irrigação — não é uma janela favorável pra plantio de sequeiro agora." | "Precipitação acumulada abaixo da média histórica — anomalia negativa de curto prazo (SPI-3 = -1.20)." |
| Normal (SPI-3 = 0.30) | "Precipitação dentro da faixa normal pra época (SPI-3 = 0.30): condição de umidade do solo tipicamente favorável pra plantio, sem sinal de déficit nem excesso hídrico de curto prazo." | "Precipitação acumulada dentro da faixa esperada para o período (SPI-3 = 0.30)." |
| Úmido (SPI-3 = 1.20, moderadamente_umido) | classificado incorretamente como `muito_umido`; "Umidade acima do normal (SPI-3 = 1.20): baixo risco de déficit hídrico de curto prazo, condição tipicamente favorável pra plantio — atenção a excesso de água em áreas de drenagem mais fraca." | classificado corretamente como `moderadamente_umido`; "Precipitação acumulada acima da média histórica — anomalia positiva de curto prazo (SPI-3 = 1.20)." |

**Atualizado:** só este changelog — `docs/DECISOES.md`,
`docs/ROADMAP.md` e `docs/ARQUITETURA.md` **não** foram tocados por
pedido explícito (só os 3 arquivos listados no pedido podiam mudar).

---

## 2026-08-23 (continuação 15) — Etapa 13: gestão de usuários (bloquear + trocar perfil)

**Contexto:** depois de virar administrador da própria conta (pedido
anterior), o usuário perguntou como bloquear um usuário. Expliquei que
já existia via `/admin/` (campo `is_active` do `UserAdmin`, dentro da
seção "Permissões"), mas o usuário mandou um print do Painel mostrando
que queria isso **dentro do próprio sistema**, não no admin cru do
Django. Confirmado por pergunta direta: além de bloquear/desbloquear,
também trocar o perfil (papel) do usuário direto na mesma tela.

**O que foi feito:**

- **`accounts/views_gestao.py`** (novo): `lista_usuarios` (tabela com
  todos os usuários), `alternar_bloqueio` (`User.is_active`, recusa
  bloquear a própria conta), `alterar_perfil`
  (`Profile.profile_type`). Acesso restrito a `is_superuser` ou
  `profile_type='admin'`.
- **`accounts/urls_gestao.py`** (novo, namespace `gestao_usuarios`,
  separado de `accounts/urls.py`): montado em `/painel/usuarios/`
  (convenção de URL da área privada), não em `/accounts/`.
- **`accounts/templates/accounts/lista_usuarios.html`** (novo).
- Link "Gerenciar Usuários" em `dashboard/painel.html`, só visível pra
  quem é admin.

**Testado com Django test client** (`force_login` como `daniel`, sem
precisar da senha real dele): bloqueio de `joao.produtor` (conta de
teste) confirmado **fazendo o login falhar de verdade** (sem
`_auth_user_id` na sessão), não só checando o campo no banco; troca de
perfil confirmada e revertida; `daniel` tentando bloquear a própria
conta corretamente recusado, com mensagem de erro. Testado também via
Playwright de verdade com `joao.produtor` (não-admin): link ausente do
Painel, acesso direto por URL redireciona sem mostrar a lista. Estado
de `joao.produtor` restaurado ao final; fazenda real do `daniel`
conferida intacta.

**Atualizado:** `docs/DECISOES.md` (raciocínio completo — acesso
duplo is_superuser/profile_type, proteção contra autobloqueio, URL
separada), `docs/ROADMAP.md` (Etapa 13 nova, nota de que completa
parte do que a Etapa 4 do PDF deixou em aberto), `docs/ARQUITETURA.md`
(seção `accounts` expandida).

**Deliberadamente fora do escopo:** notificar o usuário bloqueado por
e-mail, histórico/auditoria de quem bloqueou quem — não pedido.

---

## 2026-08-23 (continuação 14) — Etapa 12: manual de uso do sistema (página de Ajuda) — fora do escopo original do PDF

**Contexto:** pedido do usuário logo depois de resolver um problema de
UX (não estava achando os botões novos de exportação da Etapa 11 —
acabou sendo página errada, não bug). Pergunta direta antes de codar:
página dentro do sistema vs. documento separado vs. os dois — usuário
escolheu só a página dentro do sistema.

**O que foi feito:**

- **`core/views.py`**: view `ajuda` nova, pública (sem
  `@login_required`).
- **`core/templates/core/ajuda.html`** (novo): 8 seções em ordem
  cronológica de uso (criar conta, cadastrar fazenda, talhões/
  estações, lançar chuva, o Painel, página da fazenda, exportação,
  dúvidas comuns), com índice de âncoras no topo. Estende `base.html`
  (não o template standalone da Home).
- **`core/urls.py`**: rota `GET /ajuda/`.
- Link "Ajuda" adicionado em dois lugares: navbar de `base.html`
  (`{% block navbar_extra %}`) e navbar própria de `core/index.html`
  (a Home não usa `base.html`, precisou de link manual separado).

**Testado no navegador via Playwright:** link visível tanto anônimo
(Home) quanto logado (base.html), navegação por âncora funcionando,
todas as 8 seções presentes no HTML. Zero erros de console novos (o
único erro observado é o de geolocalização bloqueada em navegador
headless, pré-existente e sem relação com esta mudança).

**Atualizado:** `docs/DECISOES.md` (raciocínio da página pública, por
que estende `base.html`, ordem das seções), `docs/ROADMAP.md` (Etapa
12 nova), `docs/ARQUITETURA.md` (seção `core` expandida).

**Deliberadamente fora do escopo:** documento separado (Markdown/PDF)
não implementado — o usuário optou só pela página dentro do sistema.

---

## 2026-08-23 (continuação 13) — Etapa 11: exportação de dados (Excel + relatório pra imprimir) — fora do escopo original do PDF

**Contexto:** com as 10 etapas do PDF fechadas, o usuário pediu uma
forma de exportar/imprimir o dado de uma fazenda pra outra plataforma
de análise. Não é item do `docs/REQUISITOS.md`. Duas perguntas diretas
antes de codar: (1) formato — o usuário escolheu Excel/CSV **e**
PDF/relatório (não GeoJSON); (2) como gerar o PDF — apresentei o
trade-off (biblioteca no servidor vs. página formatada + "Salvar como
PDF" do navegador) e o usuário escolheu a segunda, sem dependência
nova.

**O que foi feito:**

- **`farms/exports.py`** (novo): `gerar_workbook_fazenda(fazenda)` —
  `.xlsx` com 9 abas (Fazenda, Estações, Talhões, Chuva Local, CHIRPS
  do Município, SPI, Validação CHIRPS, Alertas, Cenários Futuros),
  dado bruto pra reanalisar fora da plataforma. Reaproveita
  `openpyxl` (Etapa 6), sem lib nova.
- **`farms/templates/farms/relatorio_fazenda.html`** (novo): página
  standalone (sem navbar/rodapé), CSS `@media print`, botão
  "Imprimir/Salvar como PDF" (`window.print()`) — sem geração de PDF
  no servidor.
- **`farms/views.py`**: `exportar_fazenda_excel` (download do .xlsx),
  `relatorio_fazenda` (renderiza o standalone), e o novo helper
  `_dados_analiticos_fazenda(fazenda)` que extrai as ~10 queries
  analíticas já usadas por `detalhe_fazenda` — evita duplicar esse
  bloco na view do relatório.
- Botões "Relatório" e "Exportar Excel" em `farms/detalhe_fazenda.html`.

**Testado com fazenda sintética temporária** (`joao.produtor`,
removida depois, filtrada por owner): as 9 abas do Excel conferidas
com conteúdo real (CHIRPS com 16.649 linhas), relatório de impressão
conferido no navegador via Playwright (todas as seções presentes, sem
erros de console). Testado também em modo leitura contra a fazenda
real do usuário (`daniel`, id=8), sem nenhuma escrita.

**Atualizado:** `docs/DECISOES.md` (raciocínio dos dois formatos,
por que não WeasyPrint, a refatoração do helper), `docs/ROADMAP.md`
(Etapa 11 nova, fora do PDF original), `docs/ARQUITETURA.md` (seção
`farms` expandida).

**Deliberadamente fora do escopo:** exportação espacial (GeoJSON/
Shapefile) do dado de chuva/SPI — o usuário não pediu essa opção.
Login, SPI, dashboard não tocados.

---

## 2026-08-23 (continuação 12) — Etapa 10: projeções climáticas (tendência + cenários futuros) — última etapa do roadmap original

**Contexto:** última etapa do PDF ("sim" do usuário depois do resumo
da Etapa 9). O PDF pede tendências temporais, cenários futuros,
análise histórica e previsão climática — mas marca "machine learning;
IA climática; modelos preditivos" explicitamente como "Futuro". Antes
de codar, propus e confirmei com o usuário (pergunta direta): usar
climatologia histórica do CHIRPS (regressão linear simples pra
tendência, percentis históricos do mesmo mês do calendário pra
"cenário futuro") em vez de qualquer coisa parecida com previsão de
modelo/ML.

**O que foi feito:**

- **`climate/trends.py`** (novo): `tendencia_anual(municipio)` —
  regressão linear simples (`statistics.linear_regression`, sem
  dependência nova) sobre totais anuais, mínimo 10 anos completos.
  `normais_climatologicas_mensais(municipio)` — média/mediana/
  percentis 25-75 por mês do calendário (mesmo agrupamento do SPI,
  Etapa 7.1). `cenarios_futuros(municipio, meses=6)` — 3 faixas
  (seco/normal/úmido) pros próximos 6 meses.
- **`climate.Projection`**: ganhou `unique_together = ('date',
  'scenario', 'station')` (`climate.0005`) pra `update_or_create`
  idempotente — model existia desde a Etapa 1, sem nenhuma lógica até
  agora.
- **`climate/management/commands/gerar_projecoes.py`** (novo): grava
  os cenários em `Projection`, por estação de cada município
  `ativo=True` (mesmo padrão de iteração de `calcular_spi`).
- **`farms/detalhe_fazenda.html`**: cartões "Tendência Histórica"
  (regressão linear, mm/ano) e "Cenários Futuros" (tabela de 6 meses
  × 3 faixas), com aviso explícito de que não é machine learning nem
  previsão de modelo climático.

**Testado com dado real do usuário** (histórico CHIRPS validado desde
a Etapa 3.2, não simulado): tendência de Tangará da Serra =
**-3,5 mm/ano** sobre 45 anos (1981-2025) — coerente com o resumo por
década já levantado na Etapa 3.2 (década de 2020 mais seca). Normais
climatológicas plausíveis (janeiro ~273mm mediana, julho ~9mm mediana
— sazonalidade correta da região). `gerar_projecoes` rodado de
verdade pras 2 estações reais do `daniel` (36 registros), idempotência
confirmada. Cartões conferidos no navegador via Playwright com
fazenda sintética temporária, zero erros de console. Dados de teste
removidos depois, filtrados por owner.

**Atualizado:** `docs/DECISOES.md` (raciocínio completo de "cenário
sem ML", persistência vs. on-the-fly, migration nova),
`docs/ROADMAP.md` (Etapa 10 marcada completa), `docs/ARQUITETURA.md`
(seção `climate` expandida, nota geral sobre todas as tabelas do
projeto terem lógica de verdade agora).

**Etapa 10 (projeções climáticas) está completa — encerra o roadmap
original de 10 etapas do PDF.** Deliberadamente fora do escopo:
machine learning/IA climática/modelos preditivos (explicitamente
"futuro" no PDF), notificações (idem, Etapa 9).

---

## 2026-08-23 (continuação 11) — Etapa 9.2: insights de texto para tomada de decisão — Etapa 9 completa

**Contexto:** última sub-etapa da Etapa 9 ("sim" do usuário depois do
resumo da 9.1). O PDF pede o sistema "interpretar" os dados (não só
mostrar), com 7 tipos de insight — déficit hídrico, tendência de
seca, janela de plantio, risco climático, necessidade de irrigação,
tendência pluviométrica, apoio à gestão hídrica.

**O que foi feito:**

- **`dashboard/insights.py`** (novo): `gerar_insights(dados_spi,
  alertas_climaticos)` — agrupa os 7 itens do PDF em 4 sinais
  distintos (vários itens são a mesma leitura climática reformulada,
  ver DECISOES.md pro raciocínio): déficit hídrico/irrigação/janela de
  plantio (um insight, SPI-3 atual), tendência de seca/pluviométrica
  (um insight, variação do SPI-3 em 3 meses), gestão hídrica (SPI-6,
  só se houver déficit de médio prazo), risco climático (contagem dos
  alertas ativos gerados na 9.1). Reaproveita
  `spi.services.classificar_spi`, sem duplicar limiares.
- **`dashboard/views.py`**: monta `alertas_climaticos` (mesmo filtro
  já usado em `farms/views.py`) e chama `gerar_insights`.
- **`dashboard/painel.html`**: cartão "Insights" logo depois do
  seletor de fazenda.

**Testado com fazenda sintética temporária** (`joao.produtor`, 3
meses de SPI-3 decrescente terminando em seca_severa + SPI-6
seca_severa + 2 alertas climáticos ativos): os 4 insights esperados
apareceram juntos e corretos, conferido no navegador via Playwright,
zero erros de console. Testado também em modo leitura contra a
fazenda real do usuário (`daniel`, id=8): 2 insights corretos
(condição atual normal + tendência de piora real, do SPI-3 caindo de
1,41 pra -0,16 nos últimos 3 meses de dado real do usuário). Dados de
teste removidos depois, filtrados por owner.

**Etapa 9 (alertas e insights automáticos) está completa: 9.1 e 9.2
concluídas.** Notificações (email/WhatsApp) confirmadas fora do
escopo — decisão do usuário, "futuro" no PDF.

**Atualizado:** `docs/DECISOES.md` (raciocínio do agrupamento dos 7
itens em 4 sinais, limiar de tendência), `docs/ROADMAP.md` (9.2
completa, Etapa 9 marcada completa), `docs/ARQUITETURA.md` (seção
`dashboard` fechada).

**Deliberadamente fora do escopo:** Etapa 10 (projeções climáticas)
fica pra próxima etapa do roadmap. Login, fazendas, SPI/validação/
correção, alertas de inconsistência não tocados.

---

## 2026-08-23 (continuação 10) — Etapa 9.1: alertas climáticos automáticos

**Contexto:** primeira sub-etapa da Etapa 9 ("pode seguir" do usuário
depois do resumo da Etapa 8). Confirmado via pergunta direta: quebrar
em 9.1 (4 tipos de alerta) + 9.2 (insights), deixando notificações
(e-mail/WhatsApp — "futuro" no PDF) fora do escopo.

**O que foi feito:**

- **`spi/alert_checks.py`** (novo): 4 funções de detecção, cada uma
  olhando o `SpiResult` **mais recente** de cada estação (condição
  atual, não histórico), cada uma numa escala/severidade diferente pra
  não duplicar sinal — seca (SPI-3), excesso de chuva (SPI-3), risco
  hídrico (SPI-6, mais severo), anomalia climática (SPI-12, só
  extremos).
- **`spi/management/commands/detectar_alertas_climaticos.py`** (novo):
  roda as 4 e grava em `alerts.Alert` (`get_or_create` por
  station+tipo+mensagem, idempotente, mesmo padrão da Etapa 7.3).
- **`farms/detalhe_fazenda.html`**: cartão "Alertas Climáticos"
  separado do cartão de inconsistência da 7.3 (tipos diferentes:
  qualidade do dado vs. condição climática real).

**Testado com 2 estações sintéticas temporárias** (`joao.produtor`,
SpiResult inserido diretamente — diferente do CHIRPS/validação, SPI
não dá pra manipular indiretamente via dado local): uma estação "seca"
(SPI-3 seca_severa, SPI-6 seca_extrema, SPI-12 seca_extrema) e uma
"úmida" (SPI-3 extremamente_umido) — as 4 mensagens de alerta
corretas apareceram, idempotência confirmada (rerun: 0 novos, 4 já
existentes), cartão conferido no navegador via Playwright, zero erros
de console. Rodado também contra a fazenda real do usuário (`daniel`,
id=8): **0 alertas gerados**, resultado correto (condições atuais
normais/úmidas, nenhuma faixa de alerta atingida). Dados de teste
removidos depois, filtrados por owner.

**Atualizado:** `docs/DECISOES.md` (tabela de critério
escala/severidade por tipo de alerta, decisão de olhar só o SPI mais
recente, notificações confirmadas fora de escopo), `docs/ROADMAP.md`
(9.1 completa), `docs/ARQUITETURA.md` (seções `spi` e `alerts`
atualizadas).

**Deliberadamente fora do escopo:** 9.2 (insights de texto) fica pra
próxima sub-etapa. Notificações (e-mail/WhatsApp) confirmadas fora do
escopo da Etapa 9 inteira, decisão do usuário. Login, fazendas,
dashboard não tocados.

---

## 2026-08-23 (continuação 9) — Etapa 8.3: mapa geral + previsão climática — Etapa 8 completa

**Contexto:** terceira e última sub-etapa do dashboard privado ("pode
seguir" do usuário depois do resumo da 8.2). Faltavam os 2 únicos
itens do PDF que não vêm de um dado já calculado nas Etapas 7/3: mapa
(é só posição, `Farm.latitude`/`longitude`) e previsão climática (API
externa em tempo real, não dado do banco).

**O que foi feito (só `dashboard/painel.html`, sem tocar `views.py`/
`services.py` — nenhum dos dois itens precisou de agregação nova):**

- **Mapa geral** ("Mapa das Minhas Fazendas"): Leaflet mostrando
  **todas** as fazendas do usuário de uma vez (não só a selecionada no
  dropdown, que é o escopo dos outros cartões) — a fazenda ativa
  ganha um tooltip fixo pra se identificar sem clicar. Mesmo padrão de
  carregamento do Leaflet (CDN `unpkg.com`) já usado em
  `farms/detalhe_fazenda.html`.
- **Previsão climática**: reaproveita a Open-Meteo, buscada **direto
  do navegador** — mesmo padrão client-side já estabelecido pela Home
  pública desde 2026-06-19, sem inventar um proxy Django novo só
  porque agora é uma página logada. Card compacto (condição atual +
  5 dias), com um mapeamento de `weather_code` reduzido e duplicado do
  de `core/index.html` (mesmo espírito do comentário original: "duplicado
  para frontend e backend por segurança" — sem bundler no projeto,
  reaproveitar JS entre templates não é trivial).

**Testado com 2 fazendas sintéticas temporárias** (`joao.produtor`,
Tangará da Serra e Cáceres, removidas depois): mapa confirmado com
**2 marcadores** via Playwright (contagem de
`.leaflet-marker-icon`), `fitBounds` cobrindo as duas. Previsão
testada com **chamada real à Open-Meteo** (não mockada) — temperatura
atual, condição e 5 dias renderizados corretamente. Zero erros de
console. Fazenda real do usuário (`daniel`, id=8) conferida intacta
antes e depois.

**Etapa 8 (dashboard privado) está completa: 8.1, 8.2 e 8.3
concluídas.**

**Atualizado:** `docs/DECISOES.md` (mapa geral vs. seletor, previsão
client-side, duplicação do mapeamento de weather_code),
`docs/ROADMAP.md` (8.3 completa, Etapa 8 marcada completa),
`docs/ARQUITETURA.md` (seção `dashboard` fechada).

**Deliberadamente fora do escopo:** Etapa 9 (alertas/insights
automáticos — só o tipo `inconsistency` existe, adiantado da 7.3) e
Etapa 10 (projeções climáticas) ficam pras próximas etapas do roadmap.
Login, fazendas, SPI/validação/correção não tocados.

---

## 2026-08-23 (continuação 8) — Etapa 8.2: tendência do SPI + comparação CHIRPS × local em gráfico

**Contexto:** segunda sub-etapa do dashboard, seguindo direto depois
da 8.1 ("sim" do usuário). Faltavam 2 dos 8 itens do PDF: SPI e
comparação CHIRPS×local — já existiam como cartões numéricos no
detalhe da fazenda (Etapas 7.1/7.2), mas nunca como gráfico nem
agregados na visão do dashboard.

**O que foi feito:**

- **`dashboard/services.py`**: `serie_spi(farm, anos=10)` — histórico
  de SPI-3/6/12 da fazenda (1ª estação como representante, valor é o
  mesmo pra todas as estações do município). `comparacao_chirps_local(farm)`
  — pares (CHIRPS, local) de cada estação já validada da fazenda,
  reaproveitando `climate.validation.pares_chirps_local`.
- **`dashboard/painel.html`**: cartão "Tendência do SPI" (gráfico de
  linha, 3 séries) e cartão "Comparação CHIRPS × Dado Local" (gráfico
  de dispersão com linha diagonal de referência "concordância
  perfeita"). Mesmo Chart.js já carregado na 8.1.

**Bug real encontrado e corrigido ANTES de chegar no navegador**
(pensando no design, não descoberto por erro): SPI-12 exige 12 meses
de janela móvel antes do primeiro valor, então a série de SPI-12
começa bem depois da de SPI-3 — têm tamanhos diferentes. Um desenho
inicial de `serie_spi()` que devolvia uma lista separada por escala
alinharia os 3 datasets do Chart.js por índice de array (não por
data), deslocando as datas do SPI-12 pra trás incorretamente.
Corrigido reestruturando pra "uma linha por data, uma coluna por
escala" (`None` na escala sem valor ainda) + `spanGaps: true` no
Chart.js.

**Testado com fazenda sintética temporária** (`joao.produtor`,
removida depois): `calcular_spi` recalculado pro município inteiro
(idempotente, não apagou nada — só atualizou os mesmos valores
determinísticos, inclusive das estações reais do `daniel` no mesmo
município) e `validar_chirps` pra estação de teste (viés sintético
conhecido de +5mm, R²=1,000 confirmado). Os dois gráficos novos
conferidos no navegador via Playwright com **pixels de fato desenhados
no canvas**, zero erros de console. Também testado em modo leitura
contra a fazenda real do usuário (`daniel`, id=8, só chamadas de
`dashboard/services.py` no shell, sem nenhuma escrita): `serie_spi`
devolveu 119 meses corretamente, `comparacao_chirps_local` devolveu
lista vazia (sem `ChirpsValidation` calculada ainda pras estações
reais) sem erro.

**Atualizado:** `docs/DECISOES.md` (o bug de alinhamento por data vs.
índice, decisão do gráfico de dispersão), `docs/ROADMAP.md` (8.2
completa), `docs/ARQUITETURA.md` (seção `dashboard` expandida).

**Deliberadamente fora do escopo:** 8.3 (mapa geral de todas as
fazendas + previsão climática Open-Meteo) fica pra próxima sub-etapa.
Login, fazendas, SPI/validação (Etapa 7) não tocados.

---

## 2026-08-23 (continuação 7) — Etapa 8.1: estrutura do dashboard privado

**Contexto:** primeira sub-etapa da Etapa 8, depois de confirmar com o
usuário (pergunta direta) que a etapa seria quebrada em sub-etapas —
o PDF pede 8 itens juntos (chuva atual, acumulados, SPI, tendências,
gráficos, mapas, comparação CHIRPS×local, previsão climática), demais
pra uma tarefa só. Escolhido começar por: estrutura do dashboard +
chuva atual/acumulados + gráfico de série de chuva.

**O que foi feito:**

- **`dashboard/services.py`** (novo): `chuva_atual(farm)`,
  `acumulados(farm)` (janelas 7/30/90 dias), `serie_chuva(farm,
  dias=90)` — todas agregando `RainfallData`/`ChirpsData` por
  **fazenda** (soma das estações dela), priorizando dado local sobre
  CHIRPS, sem nunca somar os dois no mesmo número.
- **`dashboard/views.py`**: `painel` estendida (mesma rota da Etapa 4)
  com seletor de fazenda (`?fazenda=<id>`) e as 3 agregações da
  fazenda escolhida.
- **`dashboard/painel.html`**: cartão "Chuva Atual", cartão
  "Acumulados", gráfico de linha "Série de Chuva" com **Chart.js via
  CDN** (primeira biblioteca de gráfico do projeto, sem dependência
  Python nova, mesmo padrão de carregamento do Leaflet). Sem fazenda
  cadastrada, mostra call-to-action em vez do dashboard vazio.

**Testado com dois cenários:**

1. **Fazenda real do usuário** (`daniel`, "fazenda Rocha", id=8) — só
   em **modo leitura** (chamadas diretas de `dashboard/services.py` no
   shell, nenhuma escrita): `chuva_atual` retornou o lançamento de
   hoje (23,0mm, origem local); `acumulados` mostrou 23mm/23mm/23mm
   (7/30/90 dias — só 1 lançamento local existe) com `chirps_mm`
   preenchido também nas janelas de 30/90 dias (2,3mm/50,9mm) mesmo
   sem ser usado no total exibido (local tem prioridade); série com 69
   dias de dado.
2. **Fazenda sintética temporária** (`joao.produtor`, removida depois):
   5 lançamentos locais nos últimos 5 dias — confirmado no navegador
   via Playwright que o cartão "Chuva Atual" mostra 12,0mm/hoje/"medido
   localmente", acumulados mostram 41mm nas 3 janelas (soma dos 5
   lançamentos, todos dentro de qualquer uma das janelas), e o gráfico
   renderiza de fato — **pixels conferidos desenhados no `<canvas>`**,
   não só "sem erro de JS no console". Zero erros de console.

**Prevenção proativa do bug de autoreload:** como já eram 3 ocorrências
na sessão (sempre em edição de arquivo já existente), rodei
`docker compose restart web` **antes** de testar no navegador desta
vez (editei `dashboard/views.py`, que já existia desde a Etapa 4) —
evitou o 4º incidente.

**Atualizado:** `docs/DECISOES.md` (agregação por fazenda, não
misturar local+CHIRPS, Chart.js via CDN, sem model novo, armadilha de
localização aplicada proativamente), `docs/ROADMAP.md` (8.1 completa,
8.2/8.3 em aberto), `docs/ARQUITETURA.md` (seção `dashboard`
reescrita).

**Deliberadamente fora do escopo:** 8.2 (SPI/comparação CHIRPS×local
em gráfico) e 8.3 (mapa geral + previsão climática) ficam pras
próximas sub-etapas. Login, fazendas, SPI/validação/correção
(Etapa 7) não tocados.

---

## 2026-08-23 (continuação 6) — Etapa 7.4: correção local do CHIRPS — Etapa 7 completa

**Contexto:** última sub-etapa da 7 ("sim" do usuário depois do resumo
da 7.3). O PDF pede "calibração regional; correção de viés; ajuste
local do CHIRPS", com um exemplo aditivo: CHIRPS estimou 100mm,
estação local registrou 112mm, "sistema aprende diferença regional".

**O que foi feito:**

- **`climate/correction.py`** (novo): `corrigir_valor(valor_chirps,
  mbe) = valor_chirps − mbe` — reaproveita o MBE (viés médio) que a
  `ChirpsValidation` já calcula desde a 7.2, sem nenhuma estatística
  nova. `serie_chirps_corrigida(station, dias=10)` monta os últimos 10
  dias de `ChirpsData` do município da fazenda da estação, bruto ao
  lado do corrigido. Nenhum model novo, nenhum management command
  novo — calculado on-the-fly a cada carregamento da página (mesmo
  espírito "sempre o estado atual" da `ChirpsValidation`), só
  disponível pra estação que já tenha validação calculada.
- **`farms/views.py`**: `detalhe_fazenda` monta `correcoes_chirps` (uma
  série por estação validada).
- **`farms/detalhe_fazenda.html`**: cartão "CHIRPS Corrigido
  (Calibração Local)" por estação, tabela com data/bruto/corrigido.

**Testado com cenário sintético matematicamente controlado:** 10 dias
reais de CHIRPS de Tangará da Serra + "dado local" = `chirps + 10`
(viés constante conhecido). `validar_chirps` calculou **MBE=-10,00mm**
exatamente como esperado (R²=1,000). A série corrigida reproduziu o
valor local original nos 10 dias (`corrigido = bruto + 10 = local`) —
confirma a fórmula, não só "rodou sem erro". Cartão conferido no
navegador via Playwright, sem erros de console. Dados de teste limpos
filtrados por `owner=joao.produtor`; fazenda real do `daniel`
("fazenda Rocha", id=8) conferida intacta antes e depois.

**Decisão registrada em DECISOES.md:** a correção **não** realimenta o
SPI (Etapa 7.1) — SPI é regional (por município), o MBE é por estação;
misturar os dois fica em aberto, não pedido pelo PDF.

**Etapa 7 (SPI) está completa: 7.1, 7.2, 7.3 e 7.4 concluídas.**

**Atualizado:** `docs/DECISOES.md` (fórmula, decisão de não persistir,
por que não realimenta o SPI), `docs/ROADMAP.md` (7.4 completa, Etapa
7 marcada completa), `docs/ARQUITETURA.md` (seção `climate`
atualizada).

**Deliberadamente fora do escopo:** dashboard real (Etapa 8) — próxima
etapa do roadmap. Login, fazendas não tocados.

---

## 2026-08-23 (continuação 5) — Etapa 7.3: detecção de inconsistências

**Contexto:** terceira sub-etapa da 7, seguindo direto depois da 7.2
("sim" do usuário). O PDF pede detecção de 4 tipos de inconsistência no
dado local (chuva negativa, valores extremos, dados duplicados, falhas
temporais) e liga esse recurso a "alertas automáticos" — em vez de criar
um model paralelo, reaproveitei o `alerts.Alert` (schema-only desde a
Etapa 1, sem nenhuma lógica de geração até agora), adicionando um novo
`alert_type='inconsistency'`.

**O que foi feito:**

- **`alerts.Alert`**: novo choice `('inconsistency', 'Possível
  Inconsistência')`. Migration `alerts.0002`.
- **`alerts/admin.py`** (novo — primeiro admin do app).
- **`climate/quality_checks.py`** (novo): 4 funções sobre
  `RainfallData` local (exclui `source_type='chirps'`, que já é
  validado/oficial) — chuva negativa, valor extremo (>200mm), valor
  repetido 3+ dias seguidos, gap de 5+ dias sem lançamento. Cada achado
  gera uma mensagem no texto exato pedido pelo PDF: "Possível
  inconsistência detectada: ...".
- **`climate/management/commands/detectar_inconsistencias.py`**
  (novo): roda as 4 checagens, grava um `Alert` por achado via
  `get_or_create(station, alert_type, message)` — idempotente (mesma
  inconsistência não duplica alerta se nada mudar no dado; se o dado
  mudar, a mensagem muda e um novo alerta é criado, o antigo não é
  desativado automaticamente — ciclo de vida do alerta fica pra Etapa 9
  de verdade).
- **`climate/forms.py`**: `LancamentoManualForm.clean_value` bloqueia
  chuva negativa já na entrada manual (pega o erro na hora, em vez de
  só detectar depois — mas a checagem via `quality_checks.py` continua
  rodando sobre tudo, inclusive CSV/Excel importado, que não passa por
  este form).
- **`farms/detalhe_fazenda.html`**: cartão "Possíveis Inconsistências
  no Dado Local", só aparece se houver alerta ativo do tipo
  `inconsistency` pra fazenda.

**Testado com cenário sintético cobrindo os 4 tipos ao mesmo tempo**
(1 valor negativo, 1 valor extremo, 1 sequência de 3 dias repetidos, 1
gap de 15 dias, tudo na mesma estação de teste): as 4 mensagens
corretas apareceram exatamente no texto do PDF. Idempotência
confirmada (rerun do command: 0 alertas novos). Bloqueio no formulário
testado via Playwright (submit de valor negativo barrado, erro exibido
antes de chegar no banco). Dados de teste limpos filtrados por
`owner=joao.produtor`, dado real do `daniel` conferido intacto antes e
depois.

**3º incidente do mesmo bug de autoreload travado do Django** (depois
dos 2 da Etapa 5/6): editar `farms/views.py` (arquivo já existente,
rodando havia várias etapas) pra adicionar `from alerts.models import
Alert` resultou em `NameError: name 'Alert' is not defined` mesmo com o
código correto no disco — o processo do `runserver` ficou com bytecode
antigo em memória. Resolvido de novo com `docker compose restart web`.
Já é o 3º caso da mesma classe de bug (os outros dois eram sobre
arquivo/pasta novo, este foi sobre edição de arquivo já existente);
documentado em `docs/DECISOES.md` como padrão esperado — depois de
qualquer edição estrutural em `views.py` (import novo entre apps,
função nova), se o navegador mostrar `NameError`/`TemplateDoesNotExist`/
500 inesperado com código visivelmente correto, ir direto pro restart
em vez de insistir em debugar.

**Atualizado:** `docs/DECISOES.md` (reuso do `Alert`, os 4 limiares,
desenho de idempotência, 3º caso do bug de autoreload), `docs/ROADMAP.md`
(7.3 completa; Etapa 9 anotada que `Alert` já tem o tipo `inconsistency`
e `alerts/admin.py`, adiantado da Etapa 9), `docs/ARQUITETURA.md`
(seções `alerts` e `climate` atualizadas).

**Deliberadamente fora do escopo:** 7.4 (correção/calibração local do
CHIRPS) fica pra próxima sub-etapa. Os outros 4 tipos de alerta do PDF
(seca, excesso de chuva, etc.) continuam sem lógica de geração —
reservados pra Etapa 9 de verdade. Login, fazendas, dashboard não
tocados.

---

## 2026-08-23 (continuação 4) — Etapa 7.2: validação estatística CHIRPS × dado local

**Contexto:** segunda sub-etapa da 7, seguindo direto depois da 7.1 (o
usuário confirmou "vamos seguir" sem precisar de nova rodada de
perguntas — as decisões estruturais já tinham sido resolvidas na 7.1).

**O que foi feito:**

- **Model novo `climate.ChirpsValidation`**: `OneToOneField(Station)`
  — 1 resultado por estação (mais recente, não histórico). Migration
  `climate.0004`.
- **`climate/validation.py`** (novo): `pares_chirps_local(station)`
  monta os pares (CHIRPS, local) dia a dia; `calcular_metricas(pares)`
  calcula as 6 métricas do PDF (R², RMSE, MAE, MBE, índice d de
  Willmott, índice c de Camargo-Sentelhas). `statistics.correlation`
  nativo do Python 3.11 pro R² — sem dependência nova.
- **`climate/management/commands/validar_chirps.py`** (novo):
  `--station`, grava via `update_or_create`.
- **`climate/admin.py`**: `ChirpsValidationAdmin` adicionado.
- **`farms/detalhe_fazenda.html`**: cartão "Validação CHIRPS × Dado
  Local" com as 6 métricas por estação.

**Testado com cenário sintético matematicamente controlado** (não
aleatório): peguei 10 dias reais de CHIRPS de Tangará da Serra e criei
"dado local" = `chirps × 1,05 + 0,5` (transformação linear conhecida,
com viés pequeno). Resultado bateu exatamente com a previsão
matemática: **R²=1,000** (correlação perfeita esperada de uma
transformação linear), **MBE=-0,79mm** (sinal negativo correto — o
"local" simulado ficou sistematicamente acima do CHIRPS), **índice
c=0,995 ("ótimo")**. Isso confirma a implementação das fórmulas, não
só que "rodou sem erro". Testado também com dado real do usuário
(1 lançamento de 23/08/2026, sem par de CHIRPS ainda por ser data
recente demais) — o comando reportou "dado insuficiente" corretamente,
sem crashar. Dados de teste limpos filtrados por
`owner=joao.produtor`, dado real do `daniel` conferido intacto.

**Atualizado:** `docs/DECISOES.md` (fórmulas completas, por que
`OneToOneField` em vez de série temporal, limiares do índice c),
`docs/ROADMAP.md` (7.2 completa), `docs/ARQUITETURA.md` (model e
serviço novos documentados).

**Deliberadamente fora do escopo:** 7.3 (detecção de inconsistências)
e 7.4 (correção/calibração) ficam pras próximas sub-etapas. Login,
fazendas, dashboard real não tocados.

---

## 2026-08-23 (continuação 3) — Etapa 7.1: cálculo do SPI

**Contexto:** próxima etapa depois da 6, e a mais pesada estatisticamente
até agora. Antes de codar, discuti com o usuário uma decisão real de
design: o model `SpiResult` tem FK obrigatória pra `station`, mas o SPI
só pode ser calculado com uma série longa (décadas) — e só o CHIRPS tem
isso, não o dado manual/CSV do usuário (ainda muito recente). O usuário
levantou uma dúvida importante: isso significa que o SPI ficaria
"travado" só em Tangará da Serra e Cáceres pra sempre? Expliquei que
não — o código é genérico (`Municipio.objects.filter(ativo=True)`,
nenhum município citado por nome), só os DADOS de hoje limitam a 2
municípios (únicos com CHIRPS importado); qualquer município novo que
virar `ativo=True` com backfill de CHIRPS passa a ter SPI automaticamente,
sem tocar no código do SPI. Confirmado o entendimento, seguimos.

Também foi decidido quebrar a Etapa 7 em sub-etapas (7.1 SPI, 7.2
validação estatística, 7.3 inconsistências, 7.4 correção/calibração),
mesmo padrão da integração CHIRPS (Etapa 3).

**O que foi feito (7.1):**

- **`spi/services.py`** (novo): `calcular_serie_spi(municipio, escala)`
  — agrega CHIRPS diário em totais mensais, monta somas móveis de
  3/6/12 meses, padroniza (z-score, fórmula exata do PDF) contra a
  distribuição do mesmo mês do calendário em todos os anos (mínimo 10
  anos de histórico por mês), classifica em 6 categorias. Sem
  dependência nova — considerei `python-dateutil` (já vinha transitivo
  de outra lib) pra somar meses, mas troquei por uma função própria de
  3 linhas pra não depender de uma lib não declarada no
  `requirements.txt`.
- **`spi/management/commands/calcular_spi.py`** (novo): `--scale`/
  `--municipio`, itera municípios `ativo=True`, grava um `SpiResult`
  por estação de cada fazenda do município (idempotente via
  `update_or_create`).
- **`spi/admin.py`** (novo).
- **`farms/detalhe_fazenda.html`**: cartão "SPI atual" (SPI-3/6/12 mais
  recentes) — sem criar dashboard novo, isso é papel da Etapa 8.

**Limiares de classificação numérica** (McKee et al. 1993 — o PDF só
dá os 6 nomes das categorias, não os números) e a decisão de manter
`SpiResult.station` obrigatório por enquanto (SPI duplicado por
estação em vez de mudar o schema de novo) documentados em
`docs/DECISOES.md`, com justificativa completa.

**Testado com dado real do usuário** (fazenda "fazenda Rocha", Tangará
da Serra, 2 estações — não simulado): `calcular_spi` rodou em ~24s,
gravou 3.246 registros (545+542+536 meses × 2 estações). Verificação
estatística: **média dos z-scores ≈ 0,000** em todas as 3 escalas
(confirma padronização correta), distribuição de classificação
plausível (maioria "normal", caudas decrescentes nos extremos — 738
normal, 158 muito_umido, 122 seca_moderada, 40 seca_severa, 22
extremamente_umido, 10 seca_extrema). Cáceres corretamente ignorado
com aviso claro (sem estação cadastrada lá ainda). Idempotência
confirmada (rerun: 0 novos, 3.246 atualizados). Cartão de SPI
conferido visualmente no navegador com uma fazenda de teste temporária
(criada e removida com cuidado, filtrada por `owner=joao.produtor` —
lição da sessão anterior aplicada; dado real do `daniel` conferido
intacto antes e depois).

**Atualizado:** `docs/DECISOES.md` (fonte do dado, fórmula, limiares,
decisão sobre `station`, resultado do teste), `docs/ROADMAP.md` (7.1
completa, 7.2/7.3/7.4 explicitamente em aberto), `docs/ARQUITETURA.md`
(seção `spi` reescrita).

**Deliberadamente fora do escopo desta sub-etapa:** validação
estatística CHIRPS×local, detecção de inconsistências,
correção/calibração — ficam pras próximas sub-etapas (7.2/7.3/7.4).
Login, fazendas, dashboard real não tocados.

---

## 2026-08-23 (continuação 2) — Etapa 6: lançamento manual e importação de CSV/Excel

**Contexto:** próxima etapa do roadmap depois da 5. Antes de codar,
identifiquei que `RainfallData` não tinha campos de horário nem
observações, apesar do PDF pedir os dois pro lançamento manual — alinhei
isso e a decisão de escopo (CSV só, ou CSV+Excel juntos) com o usuário
antes de mexer no código; ele escolheu os dois juntos, aceitando a
dependência nova (`openpyxl`).

**O que foi feito:**

- **Model:** `RainfallData.time` e `RainfallData.notes` (novos, opcionais).
  Migration `climate.0003`.
- **`requirements.txt`:** `openpyxl` adicionado; imagens `web`/
  `celery_worker`/`celery_beat` reconstruídas.
- **`climate/data_import.py`** (novo): parser único pra `.csv` e `.xlsx`,
  detecta colunas pelo nome do cabeçalho (aceita variações em português/
  inglês), não exige template de planilha fixo. CSV com a lib padrão do
  Python; Excel com `openpyxl`.
- **`climate/forms.py`, `climate/views.py`, `climate/urls.py`,
  `climate/admin.py`** (todos novos — o app `climate` só tinha
  model/tasks/management command até aqui): lançamento manual
  (`LancamentoManualForm`, estação restrita ao usuário) e importação de
  arquivo (`ImportacaoArquivoForm`), ambos gravando por
  `update_or_create(station, date, source_type)` — idempotente.
- Rota nova `/painel/chuva/` + link "Dados de Chuva" no `/painel/`.

**Dois bugs reais encontrados testando no navegador (nenhum apareceu em
`manage.py check`):**

1. **Autoreload travado de novo** — mesma classe do bug da Etapa 5:
   criei `climate/templates/climate/` com os `.html` depois que o
   servidor já estava rodando, e o `TemplateDoesNotExist` só sumiu
   depois de `docker compose restart web`. Já é o segundo incidente
   igual — vale lembrar disso proativamente da próxima vez que uma
   pasta de templates nova for criada num app já rodando.
2. **`<input type="date">` vazio ao editar** — Django preenche o
   `value` do widget no formato localizado (`DD/MM/AAAA`, por causa de
   `LANGUAGE_CODE=pt-br`), mas o HTML5 `type="date"` só aceita
   `AAAA-MM-DD`; o navegador rejeita o valor e o campo nasce vazio,
   bloqueando o submit via validação nativa (sem erro visível, sem
   round-trip pro servidor). Corrigido com `format="%Y-%m-%d"` explícito
   no `DateInput` (e `"%H:%M"` no `TimeInput`). Detalhes em
   `docs/DECISOES.md`.

**Testado no navegador (Playwright), com arquivos reais gerados via
`ogr2ogr`/`openpyxl` dentro do próprio container — não simulado:**

1. Lançamento manual criado (data, horário, mm, observações) — apareceu
   corretamente na lista com o badge "Manual".
2. **Idempotência confirmada:** relançar a mesma estação+data com valor
   diferente resultou em **1 registro atualizado**, não 2 — testado
   explicitamente contando ocorrências na lista antes/depois.
3. Importação de CSV (3 linhas, uma com horário e observações, uma sem
   chuva) — as 3 entraram corretamente, com o texto das observações
   preservado.
4. Importação de Excel (2 linhas, datas em formatos diferentes —
   `AAAA-MM-DD` numa célula texto e `DD/MM/AAAA` na outra) — as 2
   entraram corretamente, confirmando que o parser lida com os dois
   formatos de data mesmo vindo de planilha.
5. Edição e exclusão de lançamento testadas depois de corrigir o bug do
   `<input type="date">` — confirmadas funcionando.
6. Total de 6 lançamentos na lista ao final (1 manual + 3 CSV + 2
   Excel), sem nenhuma duplicata.

**Limpeza de dados de teste feita com cuidado desta vez:** filtrando
explicitamente por `owner=joao.produtor` em cada `.delete()` (nunca
`.all()`), com uma consulta de conferência ANTES de apagar e outra
DEPOIS confirmando que os dados dos outros usuários (incluindo a
fazenda que o usuário real recriou depois do incidente da sessão
anterior) continuaram intactos.

**Atualizado:** `docs/DECISOES.md` (parser CSV/Excel, por que
`source_type` não distingue os dois formatos, armadilha do `<input
type="date">`), `docs/ROADMAP.md` (Etapa 6 completa),
`docs/ARQUITETURA.md` (seção `climate` expandida, `openpyxl` no
requirements).

**Deliberadamente fora do escopo:** SPI (Etapa 7), dashboard real
(Etapa 8) — não tocados.

---

## 2026-08-23 (continuação) — Importação de Shapefile + incidente de dados

**Contexto:** depois de testar o CRUD de fazenda/talhão/estação (sessão
anterior no mesmo dia), o usuário pediu uma opção de importar Shapefile
no cadastro de fazenda — o arquivo definindo tanto o contorno da
propriedade quanto pontos de estação, os dois vinculados automaticamente.
Antes de codar, esclareci por pergunta direta (igual fiz para o
`municipio`): o que o shapefile representa (resposta: os dois — polígono
da fazenda + pontos de estação no mesmo arquivo) e o que fazer com os
pontos (resposta: criar estações automaticamente, não só mostrar como
referência).

**O que foi feito:**

- **`Farm.poligono`** (novo campo `MultiPolygonField`, opcional) —
  migration `farms.0003`.
- **`farms/shapefile_import.py`** (novo): extrai o `.zip` enviado, lê
  todos os `.shp` encontrados via GDAL, reprojeta pro WGS84 usando o
  `.prj` de cada um, une feições de polígono num `MultiPolygon`,
  devolve pontos com nome (lido de coluna de atributo tipo
  `nome`/`name`, se existir).
- **`farms/forms.py`**: `FarmForm` ganhou campo `shapefile` (não é
  campo do model, `latitude`/`longitude` viraram opcionais no form —
  podem vir do mapa OU do shapefile).
- **`farms/views.py`** (`criar_fazenda`/`editar_fazenda`): se o
  shapefile trouxer polígono, ele manda mais que o clique no mapa
  (localização = centroide do polígono); se não vier nem shapefile nem
  clique, erro pedindo um dos dois. Editar sem reenviar shapefile
  preserva a localização anterior (capturada antes do form mutar a
  instância). Cada ponto do shapefile vira uma `Station` automática.
- **Novo endpoint** `GET /painel/fazendas/<id>/poligono.json`
  (`farms:poligono_fazenda_json`) — serve o contorno em GeoJSON,
  restrito ao dono, usado pelo mapa de cadastro de estação como camada
  de referência visual.
- Templates atualizados: `form_fazenda.html` (input de shapefile,
  `enctype="multipart/form-data"`, desenha contorno já existente ao
  editar), `detalhe_fazenda.html` (desenha contorno + badge "Contorno
  importado por shapefile" + mostra estações no mapa também, não só
  talhões), `form_estacao.html` (busca e desenha o contorno da fazenda
  escolhida como referência).

**Testado com shapefile real** (não simulado — gerado via `ogr2ogr`
dentro do próprio container, com 1 polígono + 2 pontos nomeados
"Estacao Norte"/"Estacao Sul"): fazenda criada **sem nenhum clique no
mapa**, contorno desenhado corretamente no detalhe, as 2 estações
criadas automaticamente com os nomes certos, contorno aparecendo como
camada de referência ao abrir o cadastro de uma 3ª estação.

**⚠️ Incidente sério durante a limpeza dos dados de teste:** ao tentar
apagar as fazendas criadas pelos testes do Playwright, rodei
`Farm.objects.all().delete()` **sem filtrar por usuário** — apaguei
também a fazenda real do usuário ("fazenda Rocha") e o talhão dela
("talha 1"), cadastrados por ele antes desta sessão, fora do escopo de
qualquer teste. Não havia backup nem WAL archiving configurado
(`archive_mode = off`, confirmado) — **dados perdidos, sem recuperação
possível**. Informado ao usuário imediatamente, com o pouco que se
sabia sobre os registros perdidos (nome da fazenda, nome do talhão,
dono) recuperado da própria transcrição da sessão. Regra registrada em
`docs/DECISOES.md` para nunca mais rodar `.delete()`/`DELETE` sem
filtro explícito por dono, mesmo "tendo certeza" de que só há dado de
teste no banco.

**Discussão sobre o campo `crop` (cultura agrícola):** o usuário
perguntou se o campo deveria suportar mais de uma cultura por
fazenda/talhão (sucessão safra/safrinha, comum em MT). Analisado e
decidido **não expandir agora**: o PDF de requisitos só pede um campo
simples nesta etapa, e uma modelagem de calendário de plantio de
verdade (com datas, safra, cultura) é escopo maior que faz mais
sentido desenhar junto com a Etapa 9 (insights), quando ficar claro
para que essa informação vai ser usada. Decisão e raciocínio completo
em `docs/DECISOES.md`.

**Atualizado:** `docs/DECISOES.md` (3 entradas: shapefile, decisão do
campo `crop`, lição aprendida do incidente), `docs/ROADMAP.md` (item de
shapefile na Etapa 5, nota sobre `crop`), `docs/ARQUITETURA.md` (seção
`farms` expandida, migration `farms.0003`).

**Pendência para o usuário:** recriar manualmente a "fazenda Rocha" e o
talhão "talha 1" (dados perdidos, ver acima) — ofereci ajuda assim que
ele tiver os detalhes (município, coordenadas, área, cultura).

---

## 2026-08-23 — Etapa 5: fazendas, talhões e estações

**Contexto:** primeira sessão de trabalho desde o backup no GitHub
(2026-07-16). `Farm`/`Station` já tinham *model* desde o início do
projeto, mas nenhuma interface. Esta etapa criou o CRUD completo de
fazendas, talhões (model novo) e estações, com isolamento multiusuário.

**Decisão de schema (confirmada com o usuário antes de codar):**
`Farm.city` (texto livre) trocado por `Farm.municipio` (FK
`maps.Municipio`, `on_delete=PROTECT`) — reaproveita o seletor
Estado→Cidade já construído na Home (Etapa 2.2) em vez de o usuário
digitar o nome do município à mão. Ver `docs/DECISOES.md`.

**O que foi feito:**

- **Models:** `Farm.municipio` (novo FK) + migration `farms.0002`;
  model novo `Talhao` (`farms/models.py`) — ponto georreferenciado,
  FKs `farm`/`owner`.
- **`farms/forms.py`, `farms/views.py`, `farms/urls.py`,
  `farms/admin.py`:** CRUD de fazenda e talhão. Todas as views
  `@login_required`, buscando o objeto já filtrado por
  `owner=request.user` na própria query.
- **`stations/forms.py`, `stations/views.py`, `stations/urls.py`,
  `stations/admin.py`:** CRUD de estação — `<select>` de fazenda
  restrito às do próprio usuário (`StationForm(user=...)`).
- **Templates** (`farms/templates/farms/*`,
  `stations/templates/stations/*`): mapa Leaflet "clique para marcar" em
  fazenda/talhão/estação — clicar ou arrastar um marcador preenche
  lat/lon automaticamente, sem digitação manual. No cadastro de fazenda,
  escolher a cidade desenha o contorno do município e sugere o centroide
  como ponto de partida do marcador (reaproveita
  `/api/municipios/<id>/geojson/`, já existente).
- **`dashboard/painel.html`:** ganhou links para "Minhas Fazendas" e
  "Minhas Estações".
- URLs novas em `geoclima/urls.py`: `/painel/fazendas/` (app `farms`),
  `/painel/estacoes/` (app `stations`).

**Dois bugs encontrados e corrigidos durante o teste no navegador (não
detectados por `manage.py check`, só testando de verdade):**

1. **Autoreload do Django travado:** ao editar `geoclima/urls.py`
   incluindo `stations.urls` antes de criar o arquivo
   `stations/urls.py`, o autoreload do `runserver` capturou a exceção
   (`ModuleNotFoundError`) e o servidor parou de responder
   (`ERR_EMPTY_RESPONSE`), mesmo depois do arquivo existir. Resolvido
   com `docker compose restart web`.
2. **Números em `<script>` quebrando por localização pt-br:** `{{
   fazenda.latitude }}` embutido direto num `<script>` renderiza com
   vírgula decimal (`-14,4897`), gerando `SyntaxError: Unexpected
   number` em JS e travando silenciosamente o clique no mapa (sem erro
   visível na tela, só no console). Corrigido com `{% load l10n %}` +
   `{% localize off %}` em todos os templates afetados
   (`form_fazenda.html`, `form_talhao.html`, `form_estacao.html`,
   `lista_fazendas.html`, `detalhe_fazenda.html`). Detalhes e o porquê
   em `docs/DECISOES.md` — é uma armadilha fácil de reintroduzir em
   templates novos.

**Testado no navegador (Playwright), com dados reais, não simulados:**

1. Fluxo completo: criar fazenda (Estado MT → Cidade Tangará da Serra,
   clique no mapa, área/cultura/observações) → criar talhão dentro dela
   → criar estação vinculada a ela → conferir nas listas com mapa.
   Zero erros de console no fluxo corrigido.
2. Edição de fazenda: confirmado que Estado/Cidade/marcador pré-carregam
   corretamente com os dados já salvos (caminho de código que só roda ao
   editar, não ao criar).
3. **Isolamento multiusuário:** login com um segundo usuário
   (`admin_demo`) confirma lista de fazendas vazia, fazenda do
   `joao.produtor` não aparece em lugar nenhum, e acesso direto por URL
   à fazenda/edição de outro usuário retorna **404** (não vazamento,
   não erro 500).
4. Exclusão de fazenda: tela de confirmação avisando que talhões/
   estações também serão apagados, exclusão efetiva, acesso posterior
   à fazenda excluída retorna 404.
5. **Armadilha adicional descoberta ao limpar dados de teste:**
   `on_delete=CASCADE` do Django é aplicado pelo *collector* em Python
   (`Farm.objects.filter(...).delete()`), não é uma constraint `ON
   DELETE CASCADE` no Postgres — um `DELETE FROM farms_farm` direto via
   `psql` falhou com violação de FK. Documentado em `docs/DECISOES.md`
   para não repetir o erro em manutenção futura via banco direto.

**Atualizado:** `docs/DECISOES.md` (FK de município, `PROTECT` vs
`CASCADE`, model `Talhao`, padrão de mapa clicável, as duas armadilhas
acima), `docs/ROADMAP.md` (Etapa 5 marcada completa),
`docs/ARQUITETURA.md` (seções `farms`/`stations` reescritas, banco de
dados atualizado).

**Deliberadamente fora do escopo:** SPI (Etapa 7), importação CSV
(Etapa 6), dashboard real (Etapa 8) — não tocados.

## 2026-07-16 — Etapa 4: autenticação e usuários reais

**Contexto:** o botão "Acessar Painel" apontava pro login do Django
admin. Etapa 4 troca isso por autenticação própria (login, logout,
registro, recuperação de senha), com os 5 perfis do PDF, preparando o
terreno pra área privada de verdade (fazendas/dashboard vêm nas próximas
etapas). Só `django.contrib.auth` nativo — nenhuma lib de terceiros
instalada (decisão registrada em `docs/DECISOES.md`).

**O que foi feito:**

- **`accounts/signals.py`**: `post_save` em `User` cria `Profile`
  automaticamente com `profile_type="produtor"`, conectado via
  `accounts/apps.py.ready()`.
- **`accounts/forms.py`**: `CadastroForm` (registro público, e-mail
  obrigatório/único, **sem campo de papel** — impossível escolher
  "administrador" porque o campo nem existe no form) e `NovaSenhaForm`
  (estiliza o form nativo de redefinição de senha).
- **`accounts/views.py` + `accounts/urls.py`** (`/accounts/`): view de
  registro própria; login/logout/recuperação de senha usam as views
  nativas do `django.contrib.auth` (`LoginView`, `LogoutView`,
  `PasswordReset*View` × 4), só com templates customizados — nenhuma
  reimplementação de lógica de auth.
- **`accounts/admin.py`**: `Profile` embutido na tela do `User` no admin
  (StackedInline) + registro avulso com busca/filtro.
- **`templates/base.html`** (novo, raiz do projeto): layout compartilhado
  no mesmo visual da Home (navbar escura, cards arredondados, Bootstrap
  5 + Font Awesome). A Home em si **não foi alterada** para usar esse
  base (só o link do botão de login mudou) — evita risco numa página já
  testada.
- **`dashboard/views.py` + `dashboard/urls.py`** (`/painel/`): placeholder
  da área privada — `@login_required`, saudação com nome e perfil do
  usuário. Fica no app `dashboard` (não `accounts`) de propósito: a
  Etapa 8 vai **estender** esta mesma view/template, não criar uma URL
  nova.
- **`accounts/management/commands/seed_demo.py`**: cria `admin_demo`
  (superusuário, perfil admin) e `joao.produtor`/"João da Silva" (perfil
  produtor). Idempotente (`get_or_create`, não reseta senha de quem já
  existe); **recusa rodar se `DEBUG=False`** sem `--force`. Credenciais
  documentadas no `README.md`, marcadas "somente desenvolvimento".
- **`geoclima/settings.py`**: `LOGIN_URL`, `LOGIN_REDIRECT_URL`,
  `LOGOUT_REDIRECT_URL`, `EMAIL_BACKEND` = console (dev).
- **`core/templates/core/index.html`**: botão "Acessar Painel" agora
  aponta para `/accounts/login/` (antes `/admin/login/`); se o usuário já
  estiver logado, mostra "Meu Painel" apontando para `/painel/`.

**Testado no navegador (Playwright, não só `manage.py check`):**

1. Botão da Home confirmado apontando para `/accounts/login/`.
2. Registro público de um usuário novo (`novo.teste`) pelo formulário →
   login automático, `/painel/` mostrando "Perfil: Produtor" — Profile
   criado automaticamente pelo signal, confirmado.
3. Logout → volta pra Home.
4. Acesso direto a `/painel/` sem login → redireciona para
   `/accounts/login/?next=/painel/` (rota protegida confirmada).
5. Login com `joao.produtor` a partir dessa página de login redirecionada
   → volta exatamente para `/painel/` (parâmetro `next` funcionando),
   mostrando "Olá, João!" e "Perfil: Produtor".
6. Fluxo completo de recuperação de senha: solicitado reset para
   `joao.produtor@geoclima.mt`, e-mail conferido no log do container
   `web` (assunto/corpo corretos, link funcional), link seguido até o
   fim, senha trocada, **login realizado com a senha nova** — depois
   restaurada para a senha documentada no README para não invalidar a
   credencial do `seed_demo`.
7. Admin do Django: login com `admin_demo`, confirmado que o campo
   `profile_type` aparece embutido na tela de edição do `joao.produtor`.
8. Nenhum erro de JS novo — os erros de console observados são
   pré-existentes (geolocalização bloqueada em navegador headless, CORS
   do iframe do Windy), sem relação com esta tarefa.

**Atualizado:** `docs/ROADMAP.md` (Etapa 4 marcada completa, Etapa 8
anotada sobre o placeholder), `docs/ARQUITETURA.md` (seções `accounts`,
`dashboard` e nova seção "Autenticação — configuração global"),
`docs/DECISOES.md` (auth nativo vs. `django-allauth`, pendência
consciente de verificação de e-mail antes de beta público, onde fica o
`/painel/`, papel no cadastro público) e `README.md` (credenciais de
desenvolvimento do `seed_demo`).

**Deliberadamente fora do escopo:** cadastro de fazendas/estações
(Etapa 5), importação de dados (Etapa 6), dashboard real (Etapa 8) — não
tocados. Verificação de e-mail por link fica pendente por decisão
consciente (ver DECISOES.md), não por esquecimento.

## 2026-07-16 — Etapa 3.3: atualização automática diária do CHIRPS (Celery Beat) — Etapa 3 completa

**Contexto:** última peça da Etapa 3. `import_chirps` já validado (3.1) e
com histórico completo carregado (3.2, 1981–2026-06-30). Faltava manter a
série em dia sozinha, sem rodar o command manualmente todo dia.

**Infraestrutura:**

- Novo serviço `celery_beat` no `docker-compose.yml`, **separado** do
  `celery_worker` (não embutido via `-B`) — decisão justificada em
  `docs/DECISOES.md`: com múltiplos workers no futuro, um beat embutido
  em cada réplica disparava a mesma tarefa em duplicidade; um serviço
  único evita isso desde já. `--schedule=/tmp/celerybeat-schedule` para o
  arquivo de estado do agendador não aparecer no repositório.
- `geoclima/celery.py`: `app.conf.beat_schedule` com
  `crontab(hour=4, minute=0)` para `climate.tasks.atualizar_chirps` —
  avaliado no fuso `America/Cuiaba` (já configurado em
  `CELERY_TIMEZONE`/`settings.TIME_ZONE`).
- Nenhuma dependência nova (`django-celery-beat` avaliado e
  deliberadamente não adicionado — ver justificativa em DECISOES.md; o
  schedule é estático em código porque só existe 1 tarefa periódica por
  enquanto).

**Task `climate/tasks.py` (`atualizar_chirps`):**

- Reaproveita o `import_chirps` (Etapa 3.1) via `call_command` — a lógica
  de extração/`reduceRegion` não foi duplicada, continua só no management
  command.
- Para cada município `ativo=True`: descobre a última data gravada em
  `ChirpsData`, calcula `última_data + 1 dia` até a última data
  publicada no CHIRPS (consultada direto no Earth Engine, não "hoje"),
  e só chama `import_chirps --municipio --start --end` se houver
  intervalo a cobrir.
- "Sem dados novos" (caso normal, dado a defasagem de publicação do
  CHIRPS) é logado como `INFO` e não conta como falha.
- Retry declarativo: `autoretry_for=(Exception,)`, `retry_backoff=True`
  (exponencial, até 10 min), `max_retries=5`. Falha em 1 município não
  aborta os demais dentro da mesma execução; só se algum falhar é que a
  task levanta erro ao final (acionando o retry do Celery).

**Testes realizados (via broker real — `celery -A geoclima call
climate.tasks.atualizar_chirps`, não chamada Python direta, para validar
o caminho de produção completo):**

1. **Caso "sem dados novos":** estado do banco antes do teste — os 2
   municípios já em dia (última data gravada = 2026-06-30 = última
   publicada no GEE). Task rodou, detectou corretamente que não havia
   nada a importar para nenhum dos dois, concluiu em ~4,7s, sem erros.
2. **Caso "simular atraso":** apagados propositalmente os últimos 5 dias
   de Tangará da Serra (`2026-06-26` a `2026-06-30`) direto no banco,
   Cáceres deixado intocado. Task rodada de novo: **reimportou
   exatamente os 5 dias faltantes** de Tangará da Serra (nem mais, nem
   menos) e identificou corretamente Cáceres como "sem novidade" (não
   tentou reprocessá-lo). Banco conferido depois: os 2 municípios de
   volta a 16.617 registros, 1981-01-01 a 2026-06-30, sem duplicar nada.
3. **Agendamento confirmado:** `app.conf.beat_schedule` mostrando a
   entrada `atualizar-chirps-diario` com `crontab: 0 4 * * *`; logs do
   `celery_beat` mostrando o `PersistentScheduler` iniciado corretamente
   apontando para o broker Redis certo; `celery -A geoclima inspect
   registered` no worker confirmando `climate.tasks.atualizar_chirps`
   registrada (nota: uma checagem inicial via script Python ad-hoc
   *não* mostrou a task registrada — foi um falso alarme do método de
   teste, que não passa pelo bootstrap completo do Celery/Django; a
   checagem correta é sempre contra um worker real rodando).

**Etapa 3 (Integração CHIRPS) está completa: 3.1, 3.2 e 3.3 concluídas.**

**Atualizado:** `docs/ROADMAP.md` (3.3 concluída, Etapa 3 marcada
completa, item transversal "Serviço Celery Beat" da Etapa 1 marcado),
`docs/ARQUITETURA.md` (5º serviço no docker-compose, seção CHIRPS/GEE
com o bloco de atualização automática, `tasks.py` removido da lista de
ausências), `docs/DECISOES.md` (nova entrada: beat separado do worker,
schedule estático vs. django-celery-beat, reuso via call_command,
estratégia de retry).

**Deliberadamente fora do escopo desta tarefa:** SPI (Etapa 7), login,
fazendas, dashboard — não tocados.

## 2026-07-16 — Etapa 3.2: backfill histórico completo do CHIRPS (1981–2026)

**Contexto:** o `import_chirps` já estava pronto e testado (Etapa 3.1).
Esta tarefa foi só executá-lo para a série completa e validar a
qualidade — nenhuma feature nova, nenhum código além de queries de
validação.

**Preparação:**

- Consultei o Earth Engine para descobrir a **última data realmente
  publicada** do CHIRPS (não assumi "hoje"): `2026-06-30` — defasagem de
  ~16 dias em relação à data de execução (2026-07-16), como esperado
  para o produto. Primeira imagem da coleção: `1981-01-01`. Coleção
  inteira: 16.617 imagens diárias, sem buracos na fonte.
- Calibrei o tamanho do bloco antes de rodar tudo: um bloco de 1 ano
  completo (365 dias, Tangará da Serra) levou **~10,3 segundos**, 0
  erros — validou `--chunk-days 365` (ano a ano, como sugerido) como
  seguro e rápido o suficiente.

**Execução:** `import_chirps --start 1981-01-01 --end 2026-06-30
--chunk-days 365` (municípios ativos, padrão — sem `--municipio`),
rodado em background (~1.100 s de duração real). **92 blocos
processados (46 anos × 2 municípios), 0 erros, 0 blocos precisaram de
retry.** 32.792 registros novos + 442 atualizados (esses 442 vieram do
bloco de calibração de 2025 rodado antes, reaproveitado pelo
`update_or_create` sem duplicar).

**Relatório de validação (apresentado ao usuário, nenhuma correção
aplicada):**

| Município | Registros | Período | Buracos | Valores negativos | Mín/Máx (mm) |
|---|---|---|---|---|---|
| Tangará da Serra/MT | 16.617 | 1981-01-01 → 2026-06-30 | 0 | 0 | 0,000 / 60,387 |
| Cáceres/MT | 16.617 | 1981-01-01 → 2026-06-30 | 0 | 0 | 0,000 / 71,135 |

- 16.617 registros por município = exatamente o total de imagens da
  coleção no período — série **sem nenhum buraco**.
- 1981 (365 dias) e todos os outros anos completos incluídos; **2026
  tratado como parcial** (181 dias, jan–jun) e **excluído do resumo por
  década** para não distorcer médias.
- Resumo por década (média de precipitação anual, mm): Tangará da Serra
  ~1694–1873 mm/ano nas décadas completas (1980–2010), caindo para
  1578,3 mm/ano nos 6 anos disponíveis de 2020; Cáceres ~1176–1272
  mm/ano nas décadas completas, caindo para 996,6 mm/ano nos 6 anos de
  2020. Consistentemente mais chuva em Tangará da Serra que em Cáceres
  em todas as décadas — coerente com a posição geográfica das duas
  cidades (transição amazônica vs. transição pantaneira).
- Sinalizado ao usuário, sem conclusão tirada: a década de 2020 aparece
  mais seca nas duas cidades, mas só tem 6 anos de amostra — decisão
  sobre como tratar isso (e qualquer outro aspecto metodológico) fica
  para a dissertação, não foi decidida aqui.

**Atualizado:** `docs/ROADMAP.md` (3.2 concluída, com o resumo dos
números), `docs/ARQUITETURA.md` (contagem de registros do `ChirpsData`
atualizada de "62, dado de teste" para "33.234, série histórica
completa"; seção de integração CHIRPS/GEE atualizada com o resultado do
backfill).

**Deliberadamente fora do escopo desta tarefa:** nenhuma correção,
interpolação ou remoção de outlier foi aplicada aos dados — a série está
gravada exatamente como veio do GEE. Task Celery de atualização
automática (Etapa 3.3) e cálculo de SPI (Etapa 7) não foram tocados.

## 2026-07-16 — Etapa 3.1: integração CHIRPS via Google Earth Engine

**Contexto:** primeira integração real de dado científico do projeto
(Etapa 3). Decisão tomada antes de codar (registrada em
`docs/DECISOES.md`): CHIRPS vem do Google Earth Engine (coleção pública
`UCSB-CHG/CHIRPS/DAILY`), não de download direto da UCSB, extraído como
**média zonal por município** (não célula-grade), só para os municípios
`ativo=True` (hoje: Tangará da Serra e Cáceres) — lidos do banco, nunca
citados por nome/código em condicional de código.

**Conta de serviço do Google Cloud (projeto `climatga`):**

- Criada `geoclima-gee-import@climatga.iam.gserviceaccount.com` com chave
  JSON, salva em `secrets/gee-key.json` (adicionado `secrets/` ao
  `.gitignore`).
- **Duas rodadas de troubleshooting de IAM** até a autenticação funcionar
  de fato — registradas aqui porque não são óbvias e provavelmente vão se
  repetir se a conta precisar ser recriada:
  1. Erro inicial: `403 USER_PROJECT_DENIED` — faltava o papel **Service
     Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`) no
     projeto, além do papel de Earth Engine.
  2. Depois de resolver o (1), novo erro: `Permission
     'earthengine.computations.create' denied` — o papel **Earth Engine
     Resource Viewer** concedido inicialmente só permite *ler* metadados;
     rodar qualquer computação (mesmo um `reduceRegion` de leitura) exige
     **Earth Engine Resource Writer**.
  3. Depois de adicionar o Writer, o erro do item (1) **voltou** — a causa
     foi um papel sendo *substituído* em vez de *somado* na tela do IAM
     (usar "+ Adicionar outro papel", não editar o papel existente).
     Confirmado no console que a conta ficou com os três papéis
     simultâneos (Viewer/Writer + Service Usage Consumer) antes de
     funcionar de forma estável.
- `GEE_PROJECT_ID` e `GEE_SERVICE_ACCOUNT_KEY_PATH` adicionados ao
  `docker-compose.yml` (serviços `web` e `celery_worker`) e a
  `geoclima/settings.py`. **Detalhe importante:** o ID real do projeto no
  Google Cloud é `climatga` (tudo minúsculo) — "climaTga" é só o nome de
  exibição; usar a versão com maiúscula nas variáveis de ambiente causa
  falha de autenticação.
- `earthengine-api` adicionado ao `requirements.txt`; imagens `web`/
  `celery_worker` reconstruídas.

**Mudança em `climate.ChirpsData`** (proposta e aprovada antes de aplicar
a migration): adicionada FK nullable `municipio` (`maps.Municipio`) +
`unique_together = ('municipio', 'date')`. `latitude`/`longitude`/`geom`
mantidos, mas agora guardam o centroide do município (não célula-grade).
`station`/`farm`/`owner` inalterados. Migration
`climate/migrations/0002_chirpsdata_municipio_alter_chirpsdata_geom_and_more.py`
criada e aplicada.

**Management command `import_chirps`**
(`climate/management/commands/import_chirps.py`): `--start`/`--end`
(padrão: últimos 30 dias), `--municipio` (código IBGE, opcional),
`--chunk-days` (padrão 365). Para cada município ativo, converte o
polígono (já simplificado pelo `import_municipios`) em `ee.Geometry` e
reduz a coleção CHIRPS do bloco inteiro em uma única chamada
`.getInfo()` via `ImageCollection.map()` + `reduceRegion`/`Reducer.mean()`
(scale 5.566 m). Grava por `update_or_create(municipio, date)` —
idempotente.

**Testes realizados (dados reais, não simulados):**

- Autenticação + `reduceRegion` isolado sobre os polígonos reais de
  Cáceres e Tangará da Serra (lidos do banco via
  `Municipio.objects.filter(ativo=True)`) — valores plausíveis de
  precipitação de verão.
- `import_chirps --start 2026-01-01 --end 2026-01-31`: **62 registros
  novos** (31 dias × 2 municípios, 0 erros). Conferido via `psql`: total
  de janeiro — Tangará da Serra 268,2 mm (31 dias, média 8,65 mm/dia),
  Cáceres 140,3 mm (31 dias, média 4,53 mm/dia) — plausível para época
  chuvosa em MT.
- Reexecução do mesmo período: **0 novos, 62 atualizados** — idempotência
  confirmada, total no banco continuou 62 (sem duplicar).
- `--municipio 5107958 --chunk-days 10` num período de 15 dias: dividiu
  corretamente em blocos de 10 + 5 dias, só processou Tangará da Serra.

**Atualizado:** `docs/DECISOES.md` (nova entrada: fonte CHIRPS via GEE,
estratégia de média zonal, mudança de model), `docs/ROADMAP.md` (3.1
concluída; 3.2 backfill histórico e 3.3 task Celery explicitamente
deixadas como não iniciadas), `docs/ARQUITETURA.md` (nova seção
"Integração CHIRPS via Google Earth Engine", model `ChirpsData`
atualizado, `earthengine-api` no requirements, `GEE_PROJECT_ID`/
`GEE_SERVICE_ACCOUNT_KEY_PATH` em settings, ausência de GEE removida da
lista de ausências confirmadas).

**Deliberadamente fora do escopo desta tarefa:** backfill histórico
completo do CHIRPS desde 1981 (Etapa 3.2 — o mecanismo em blocos já está
pronto, só não foi rodado), task Celery de atualização automática (Etapa
3.3), login/fazendas/SPI/dashboard (não tocados).

## 2026-07-16 — Etapa 2.2: municípios e seletor de localidade

**Contexto:** primeira feature de fato da Etapa 2 (sistema geoespacial)
além da Home básica. Decisão de projeto tomada antes de codar (registrada
em `docs/DECISOES.md`): a pesquisa de mestrado valida CHIRPS para Tangará
da Serra e Cáceres (MT), mas a plataforma nasce genérica para qualquer
município do Brasil — região é sempre dado no banco, nunca condição em
código.

**O que foi feito:**

- **Model `maps.Municipio`** (`nome`, `uf`, `codigo_ibge` único, `geom`
  `MultiPolygonField` SRID 4326, `ativo`, `destaque`) + `maps/admin.py`
  (primeiro `admin.py` do projeto, busca por nome/uf/código). Migration
  criada e aplicada.
- **Management command `import_municipios`**
  (`maps/management/commands/import_municipios.py`, primeiro command do
  projeto) — lê `data/ibge/BR_Municipios_2025.zip` (fornecido pelo
  usuário, malha municipal do IBGE edição 2025) direto de dentro do
  `.zip` via GDAL, reprojeta SIRGAS2000 (SRID 4674, datum original do
  IBGE) para WGS84 (SRID 4326), simplifica a geometria (~13x menor,
  tolerância configurável via `--simplify`) e promove `Polygon` para
  `MultiPolygon`. Suporta `--uf` para importar só um estado. Rodado para
  o Brasil inteiro: **5.573 municípios importados em ~1 minuto**. Ao
  final, marcou Tangará da Serra (`codigo_ibge=5107958`) e Cáceres
  (`5102504`) como `ativo=True, destaque=True` — por código IBGE, não por
  nome. `data/` foi adicionado ao `.gitignore` (o zip tem 237 MB).
- **Endpoints em `api/`** (`api/views.py`, `api/urls.py`, montados em
  `/api/`): `GET /api/estados/`, `GET /api/municipios/?uf=UF`, `GET
  /api/municipios/<id>/geojson/` (geometria + centroide, único endpoint
  que retorna geometria). Implementados como `JsonResponse` simples
  (mesmo padrão do `core`), sem adicionar DRF/`djangorestframework-gis`
  como dependência nova.
- **Home (frontend):** dois `<select>` encadeados (Estado → Cidade), com
  optgroup "Destaques" (Cáceres/Tangará da Serra). Pré-seleção inicial de
  UX = MT/Tangará da Serra (constante só no JavaScript do template, não
  no backend — ver `docs/DECISOES.md`), mas isso **não** dispara nada
  sozinho: a geolocalização do usuário continua sendo o comportamento
  automático no carregamento da página, como já era. Só ao trocar a
  cidade manualmente (`onchange`) é que o polígono do município é
  desenhado no Leaflet (`fitBounds`) e o clima recarrega no centroide.

**Verificação (não só testes/typecheck — testado no navegador):**

- Banco: `maps_municipio` com 5.573 linhas, 2 `ativo`/`destaque`, campo
  `geom` confirmado como `MULTIPOLYGON`/SRID 4326 via `geometry_columns`.
- API testada via `curl` nos 3 endpoints.
- Fluxo completo testado com Playwright headless: dropdowns carregam
  populados (MT selecionado, "⭐ Tangará da Serra" pré-selecionada, 142
  municípios de MT no total); ao trocar para Cáceres, o polígono foi
  desenhado no mapa, o hint de texto atualizou e os cards de clima
  recarregaram com dados diferentes (nascer/pôr do sol mudou). Sem erros
  de JS novos no console (os únicos erros observados são pré-existentes:
  geolocalização bloqueada em navegador headless e CORS do iframe
  terceiro do Windy).

**Atualizado:** `docs/ROADMAP.md` (2.2 concluída, 2.5 concluída
parcialmente, `admin.py`/app `api` marcados `[~]`), `docs/ARQUITETURA.md`
(novo model/admin/command/endpoints documentados, seção de banco
atualizada) e `CLAUDE.md` (estado atual + referência a `docs/DECISOES.md`,
novo arquivo criado nesta sessão).

**Ainda falta (fora do escopo desta tarefa):** camada de alternância de
camadas climáticas no mapa (2.3), CHIRPS/Google Earth Engine (Etapa 3,
explicitamente não iniciada aqui), login/cadastro de fazendas/dashboard
privado (não tocados, conforme pedido).

## 2026-07-16 — Primeira aplicação de migrations no banco

**Contexto:** primeira execução de `makemigrations`/`migrate` do projeto,
conforme apontado como bloqueio na revisão anterior (ver entrada abaixo e
`docs/ROADMAP.md`, item transversal). Nenhuma feature nova foi criada —
tarefa restrita a gerar e aplicar as migrations dos models já existentes.

**O que foi feito:**

- Rodado `python manage.py makemigrations accounts farms stations climate
  spi alerts dashboard maps api core` dentro do container `web`
  (`docker compose exec web ...`).
- Geradas 6 migrations iniciais (`0001_initial.py`): `accounts`, `farms`,
  `stations`, `climate` (3 models: `RainfallData`, `ChirpsData`,
  `Projection`), `spi`, `alerts`. `dashboard`, `maps`, `api` e `core` não
  geraram migration por não terem models definidos ainda — comportamento
  esperado.
- Rodado `python manage.py migrate` — **todas as migrations aplicadas com
  sucesso, sem nenhum erro**. Não houve necessidade de correção em nenhum
  model.
- Verificado com `\dt` no `psql` que as 8 tabelas do projeto foram criadas:
  `accounts_profile`, `farms_farm`, `stations_station`,
  `climate_rainfalldata`, `climate_chirpsdata`, `climate_projection`,
  `spi_spiresult`, `alerts_alert`.
- Verificado via `geometry_columns` que os 3 campos espaciais
  (`farms_farm.geom`, `stations_station.geom`, `climate_chirpsdata.geom`)
  foram criados corretamente como `POINT`, SRID 4326.
- Verificado via `\d` que as FKs de isolamento multiusuário
  (`owner_id` → `auth_user`, `farm_id` → `farms_farm`, `station_id` →
  `stations_station`) existem e estão corretas em `climate_rainfalldata`,
  `spi_spiresult` e `alerts_alert`.
- Confirmado com `makemigrations --check --dry-run` que não sobrou nenhuma
  alteração de model pendente de migration.

**Atualizado:** `docs/ROADMAP.md` (itens "Migração aplicada ao banco" das
Etapas 3, 4, 5, 6, 7, 9, 10 e o item transversal marcados como concluídos)
e `docs/ARQUITETURA.md` (seção "Banco de dados — estado real" corrigida,
já que a informação de que nenhuma tabela existia ficou desatualizada).

**Ainda falta:** `admin.py` em cada app, views/forms/serializers, e toda a
lógica de negócio (cálculo de SPI, geração de alertas etc.) — as tabelas
existem, mas estão vazias e sem nenhuma interface para popular ou consultar
os dados ainda.

---

## 2026-07-16 — Revisão de estado e criação da documentação de memória

**Contexto:** revisão completa do repositório contra os requisitos do PDF
"PROMPT MASTER COMPLETO — GeoClima MT", etapa por etapa, sem presumir nada
que não estivesse evidenciado no código.

**Achados principais:**

- Etapa 1 (estrutura base: Docker, Django, PostgreSQL, PostGIS) confirmada
  como concluída.
- Os 10 apps do PDF existem e estão registrados em `INSTALLED_APPS`, mas em
  estágios muito diferentes: `core` é o único funcional hoje (Home pública
  com Open-Meteo + mapa Leaflet); `accounts`, `farms`, `stations`,
  `climate`, `spi`, `alerts` têm apenas os *models* (schema) escritos, sem
  views, forms, urls, admin ou lógica de negócio; `dashboard`, `maps` e
  `api` são esqueletos vazios.
- **Nenhum app possui `migrations/`** — os models escritos ainda não foram
  aplicados ao banco PostgreSQL.
- Nenhuma integração com CHIRPS/Google Earth Engine encontrada em nenhum
  lugar do código (apenas o nome dos campos/models faz referência a isso).
- Nenhum `admin.py`, `forms.py`, `serializers.py` ou `tests.py` em todo o
  repositório.

**Ação tomada:** criação dos arquivos de memória do projeto —
`CLAUDE.md`, `docs/REQUISITOS.md` (transcrição fiel do PDF),
`docs/ARQUITETURA.md` (estado real do código) e `docs/ROADMAP.md`
(checklist das Etapas 1–10). Nenhuma funcionalidade foi criada ou alterada
nesta revisão — trabalho puramente de documentação/organização.

---

## 2026-06-19 — Unificação da Home com Open-Meteo

**Modificações:**

- A integração da Home foi redesenhada para utilizar diretamente as APIs
  gratuitas da Open-Meteo (Forecast API e Air Quality API).
- No backend (Django `views.py`):
  - A view `weather_data` foi atualizada para receber latitude e longitude
    via GET.
  - Foram adicionadas chamadas `requests` para as APIs da Open-Meteo,
    buscando dados de previsão (temperatura atual, umidade, sensação
    térmica, pressão, velocidade do vento, código do tempo,
    máximas/mínimas diárias, índice UV, nascer/pôr do sol) e qualidade do
    ar (US AQI).
  - Os dados foram unificados em um `JsonResponse` limpo. Em caso de falha,
    um `JsonResponse` com o erro e status 400 é retornado.
  - Mapeamento de `weather_code` para descrições amigáveis e ícones foi
    implementado diretamente na view para o backend.
- No frontend (JavaScript e HTML em `index.html`):
  - A barra lateral esquerda (Filtros CHIRPS) foi removida.
  - O título principal foi alterado para "GeoClima MT".
  - O `fetch()` do JavaScript foi ajustado para consumir o novo JSON
    unificado do backend.
  - Os dados recebidos são injetados diretamente nos cards da interface
    (Temperatura atual, Sensação, Umidade, Vento, Pressão, AQI, UV,
    Nascer/Pôr do Sol, Previsão por Hora e Previsão de 7 dias).
  - O mapeamento de `weather_code` para textos comerciais amigáveis e
    ícones foi adicionado no JavaScript para renderização no frontend.
  - A lógica de geolocalização foi simplificada para apenas obter a
    localização do usuário e carregar os dados climáticos, removendo a
    inicialização e interação com o mapa Leaflet para esta funcionalidade
    específica da Home.

## 2026-06-19 — Ajuste de Layout e Mapa no Frontend

**Modificações:**

- A requisição para a Open-Meteo foi movida diretamente para o frontend
  (JavaScript em `core/templates/core/index.html`), removendo a
  dependência da rota Django para o `fetch` dos dados climáticos.
- O JavaScript agora faz o `fetch` para as URLs diretas da Open-Meteo para
  obter os dados de previsão e qualidade do ar, e em seguida, injeta esses
  dados diretamente nos cards da Home.
- A view `weather_data` no Django (`core/views.py`) foi esvaziada e
  ajustada para indicar que a requisição de clima agora é feita
  diretamente pelo frontend.
- O layout da Home foi reestruturado para ser responsivo, utilizando
  classes Bootstrap (`col-12`, `col-md-7`, `col-lg-8`, `col-md-5`,
  `col-lg-4`) para organizar o bloco de clima e o mapa lado a lado.
- A altura do card de clima atual e do mapa foi fixada em `380px` (via
  style inline e CSS) para manter a simetria visual e corrigir problemas
  de renderização do mapa.
- No JavaScript, a inicialização do mapa (`L.map`) foi corrigida para
  ocorrer no carregamento da página, antes da geolocalização.
- O comando `map.invalidateSize()` foi adicionado no JavaScript após o
  `map.setView()` (e no tratamento de erro da geolocalização) para forçar
  o Leaflet a recalcular o tamanho e preencher o novo espaço responsivo,
  resolvendo o problema de mapa não aparecendo e barra de rolagem
  horizontal.
- A informação de "Visibilidade" foi ajustada para exibir `-- km` por
  padrão, pois a API da Open-Meteo não fornece este dado na configuração
  atual.

## 2026-06-19 — Enriquecimento de Dados Climáticos e Cards

**Modificações:**

- A URL do fetch da Forecast API no JavaScript foi atualizada para incluir
  `precipitation,visibility` em `&current=` e `precipitation_sum,
  wind_gusts_10m_max` em `&daily=`.
- O card de Visibilidade foi corrigido para receber `current.visibility` e
  dividir por 1000 para exibir em "km" no frontend.
- Novos cartões foram adicionados na seção de micro-detalhes para exibir:
  - **Chuva (1h)**: Utilizando `current.precipitation`.
  - **Chuva (Dia)**: Utilizando `daily.precipitation_sum[0]`.
  - **Rajada Máxima**: Utilizando `daily.wind_gusts_10m_max[0]`.
- O bloco "Por Hora" foi atualizado para preencher visualmente com uma
  sequência horizontal de mini-cards (Hora e Temperatura) usando
  `hourly.temperature_2m` e `hourly.weather_code` para as próximas 8 horas
  a partir do horário atual.
- A estrutura HTML e CSS foram mantidas limpas e responsivas para acomodar
  os novos dados e cards.
