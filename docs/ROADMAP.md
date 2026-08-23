# Roadmap — GeoClima MT

> Checklist das 10 etapas definidas em [REQUISITOS.md](REQUISITOS.md).
> `[x]` = confirmado no código (data ao lado de cada item/seção).
> `[~]` = parcial (existe algo, mas incompleto — detalhe abaixo do item).
> `[ ]` = não iniciado (nenhuma evidência encontrada no código).
> Detalhes técnicos de cada item em [ARQUITETURA.md](ARQUITETURA.md).
> Última sessão de trabalho: 2026-08-23 (Etapa 5).

## Etapa 1 — Estrutura base (Docker, Django, PostgreSQL, PostGIS)

- [x] `Dockerfile` com dependências GDAL/PostGIS
- [x] `docker-compose.yml` com serviços `db` (PostGIS), `redis`, `web`,
      `celery_worker`
- [x] Django configurado com `django.contrib.gis` + backend PostGIS
- [x] 10 apps criados e registrados em `INSTALLED_APPS` (core, accounts,
      farms, stations, climate, spi, alerts, dashboard, maps, api)
- [ ] Serviço `nginx` no `docker-compose.yml` (citado nos requisitos, ainda
      não presente — usando `runserver` diretamente)
- [x] Serviço Celery Beat (tarefas agendadas) — adicionado em 2026-07-16
      junto com a Etapa 3.3 (única tarefa agendada até agora é o CHIRPS)

## Etapa 2 — Sistema geoespacial (mapas, municípios, Leaflet)

- [x] 2.1 Home pública com mapa Leaflet + OpenStreetMap, responsivo,
      geolocalização do usuário com marcador
- [x] 2.2 Municípios e seletor de localidade (2026-07-16) — malha
      municipal completa do Brasil (5.573 municípios, IBGE 2025) importada
      em `maps.Municipio`; seletor Estado→Cidade encadeado na Home; ao
      escolher a cidade, desenha o polígono no Leaflet e recarrega o
      clima no centroide. Estrutura nacional/genérica por design — ver
      [DECISOES.md](DECISOES.md). Só Tangará da Serra e Cáceres (MT) têm
      `ativo=True`/`destaque=True` hoje.
- [ ] 2.3 Alternância de camadas climáticas no mapa
- [~] 2.4 Mapas meteorológicos — radar/satélite via iframe Windy **feito**;
      os 4 cards "Satélite / Queimadas / Chuva Acumulada / Temperatura"
      (que eram links `#` sem função) foram **removidos da Home em
      2026-08-23**, a pedido do usuário, em vez de mantidos como
      placeholder — este sub-item volta a ficar em aberto se algum dia
      esses mapas forem implementados de verdade
- [x] 2.5 App `maps` com model/admin/management command próprios (`views`
      do seletor ficaram no app `api`, não no `maps` — ver ARQUITETURA.md)

## Etapa 3 — Integração CHIRPS (download, importação, armazenamento) ✅ COMPLETA (2026-07-16)

- [x] 3.1 Integração via Google Earth Engine (2026-07-16) — conta de
      serviço autenticada (projeto `climatga`); `climate.ChirpsData` ganhou
      FK `municipio` (nullable) + `unique_together=('municipio','date')`;
      management command `import_chirps` (`--start`/`--end`/`--municipio`/
      `--chunk-days`) calcula média zonal diária (`reduceRegion` +
      `Reducer.mean()`) sobre o polígono de cada município `ativo=True`,
      via `ImageCollection.map()` (1 chamada de rede por bloco, não por
      dia). Testado com janeiro/2026 para os 2 municípios ativos (62
      registros, valores conferidos no banco) e idempotência confirmada
      (rerun não duplica). Ver [DECISOES.md](DECISOES.md).
- [x] 3.2 Backfill histórico completo do CHIRPS (2026-07-16) — 1981-01-01
      a 2026-06-30 (última data publicada no CHIRPS; sem zeros falsos para
      dias não publicados), blocos de 365 dias, 92 blocos processados
      (46 anos × 2 municípios ativos), **0 erros/retries**. 16.617
      registros por município, **0 buracos**, **0 valores negativos**,
      série climatologicamente plausível e estável por década (ver
      relatório completo em [HISTORICO.md](HISTORICO.md)). Nenhuma
      correção/interpolação aplicada — dado bruto do GEE, como veio.
- [x] 3.3 Task Celery de atualização diária automática do CHIRPS
      (2026-07-16) — serviço `celery_beat` separado do worker (ver
      DECISOES.md); `climate.tasks.atualizar_chirps` agendada via
      `crontab(hour=4, minute=0)` em `America/Cuiaba`
      (`geoclima/celery.py`, `app.conf.beat_schedule`). Para cada
      município ativo, calcula o próximo dia após a última data gravada
      e chama `import_chirps` (via `call_command`, sem duplicar a lógica
      de extração) só para o intervalo faltante. Retry automático com
      backoff (`autoretry_for` + `retry_backoff`, max 5 tentativas).
      Testado de ponta a ponta via broker real (`celery call`, não
      chamada Python direta): (a) confirmado que detecta "sem dados
      novos" corretamente no estado atual (ambos municípios já em dia,
      2026-06-30); (b) apagados os últimos 5 dias de Tangará da Serra no
      banco, rodada de novo — reimportou **exatamente** os 5 dias
      faltantes (2026-06-26 a 2026-06-30) e não tocou em Cáceres
      (corretamente identificado como sem novidade).
- [ ] Download/importação de CHIRPS bruto por célula-grade (não priorizado
      — a extração por média zonal municipal via GEE cobre a necessidade
      atual; ver DECISOES.md sobre por que célula-grade ficou de fora)

## Etapa 4 — Login e usuários ✅ COMPLETA (2026-07-16)

- [x] Schema `Profile` definido em `accounts/models.py` com os 5 perfis do
      PDF (admin, pesquisador, produtor, técnico, visitante)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `accounts_profile`)
- [x] Tela de registro (`/accounts/registro/`) — form próprio sem campo de
      papel; login automático após cadastrar, redireciona pro `/painel/`
- [x] Tela de login própria (`/accounts/login/`) — botão "Acessar Painel"
      da Home não aponta mais para `/admin/login/`
- [x] Recuperação de senha — fluxo nativo do Django por e-mail (4 telas:
      solicitar, confirmação de envio, redefinir, concluído). Backend de
      e-mail = console em desenvolvimento (aparece no log do container
      `web`); trocar para SMTP real antes de produção — ver DECISOES.md.
- [x] Criação automática do `Profile` (signal `post_save` em `User`,
      `accounts/signals.py`), papel padrão `produtor`. Registro público
      **não pode** escolher "administrador" — o campo nem existe no form.
- [x] `admin.py` do `accounts` — `Profile` embutido na tela do `User`
      (admin consegue trocar o papel de qualquer usuário) + registro
      avulso de `Profile` com busca/filtro.
- [x] Proteção de rota privada — `/painel/` (app `dashboard`, placeholder
      da Etapa 8) exige login (`@login_required`) e volta pra lá depois
      do login via `?next=`.
- [x] `seed_demo` (management command em `accounts`) — cria `admin_demo`
      (superusuário, perfil admin) e `joao.produtor`/"João da Silva"
      (perfil produtor), idempotente, recusa rodar com `DEBUG=False` sem
      `--force`. Credenciais documentadas no `README.md`.
- [ ] Sistema de permissões por perfil granular (hoje só existe o *papel*
      gravado no `Profile`; ainda não há checagem de permissão por
      funcionalidade/view baseada nele — fica para quando a área privada
      de verdade, Etapas 5–9, começar a ter views que precisem disso)
- **Pendência consciente:** verificação de e-mail por link não
      implementada — aceitável para dev/beta fechado, precisa ser
      resolvida antes de beta público. Ver DECISOES.md.

## Etapa 5 — Fazendas e estações ✅ COMPLETA (2026-08-23)

- [x] Schema `Farm` (2026-08-23 — `city` texto livre trocado por FK
      `municipio` → `maps.Municipio`; `city` continua na tabela por
      compatibilidade, sem uso no formulário. Ver [DECISOES.md](DECISOES.md))
- [x] Schema `Station` definido (tipos: Davis, Ecowitt, Ambient, IoT, manual,
      CSV; `geom` PostGIS, FKs `farm`/`owner`)
- [x] Model novo `Talhao` (2026-08-23 — não existia antes; `farms/models.py`,
      ponto georreferenciado, FKs `farm`/`owner`)
- [x] Migração aplicada ao banco (`farms.0002` — FK `municipio`, model
      `Talhao`)
- [x] Views/forms de cadastro de fazenda (`farms/views.py`,
      `farms/forms.py`) — nome, Estado→Cidade (reaproveita o seletor da
      Home), área, cultura, observações; localização marcada clicando/
      arrastando um marcador no mapa Leaflet (sem digitar lat/lon à mão)
- [x] Views/forms de cadastro de talhão — mesmo padrão de mapa, dentro da
      página de detalhe da fazenda
- [x] Views/forms de cadastro de estação (`stations/views.py`,
      `stations/forms.py`) — `<select>` de fazenda restrito às fazendas
      do próprio usuário; mapa recentraliza ao trocar a fazenda escolhida
- [x] Visualização de fazendas no mapa — lista "Minhas Fazendas" com mapa
      Leaflet de todas as fazendas do usuário; detalhe da fazenda com
      mapa da sede + talhões
- [x] CRUD completo (criar/editar/excluir) para fazenda, talhão e
      estação, com tela de confirmação antes de excluir. Excluir fazenda
      cascateia talhões e estações (aviso explícito na confirmação)
- [x] Isolamento multiusuário testado no navegador com dois usuários
      diferentes: lista vazia para quem não tem fazenda, acesso direto
      por URL a fazenda de outro usuário retorna 404
- [x] `admin.py` em `farms` e `stations` (inlines, autocomplete,
      busca/filtro)
- [x] Importação de Shapefile no cadastro de fazenda (2026-08-23) —
      upload opcional de `.zip` (.shp/.shx/.dbf/.prj), convive com o
      clique manual no mapa. Polígono(s) do arquivo viram
      `Farm.poligono` (novo campo `MultiPolygonField`, une múltiplas
      feições); pontos viram `Station` automaticamente (nome lido do
      shapefile quando existe coluna de atributo tipo `nome`). Contorno
      mostrado no detalhe da fazenda e como camada de referência no
      cadastro de estação (`farms:poligono_fazenda_json`). Testado com
      shapefile real (1 polígono + 2 pontos nomeados via `ogr2ogr`).
      Ver [DECISOES.md](DECISOES.md).
- [~] Campo `crop` (cultura agrícola) continua um único texto por
      fazenda/talhão — avaliado e **deliberadamente não expandido**
      para um calendário de sucessão de safra/safrinha nesta etapa; fica
      pra quando a Etapa 9 (insights) definir o que realmente precisa.
      Ver [DECISOES.md](DECISOES.md).

## Etapa 6 — Importação CSV e dados manuais ✅ COMPLETA (2026-08-23)

- [x] Campo `source_type` em `RainfallData` já contemplava `manual` e
      `imported_csv`
- [x] Migração aplicada ao banco (2026-07-16 — tabela `climate_rainfalldata`;
      2026-08-23 — `climate.0003` acrescentou `time`/`notes`, pedidos pelo
      PDF e ausentes até então)
- [x] Formulário de lançamento manual de chuva (`climate/views.py`,
      `climate/forms.py` — primeiros do app `climate`, que só tinha
      model/tasks/command até aqui): estação (só as do usuário), data,
      horário opcional, mm, observações. Idempotente (`update_or_create`
      por estação+data+origem — relançar o mesmo dia atualiza, não duplica)
- [x] Importador de CSV e **Excel juntos** (`climate/data_import.py`,
      dependência nova `openpyxl`) — mesmo parser pros dois formatos,
      detecta colunas pelo nome do cabeçalho (aceita variações comuns em
      português/inglês), não exige template rígido de planilha
- [x] Histórico de lançamentos com editar/excluir, mesmo padrão de
      fazenda/talhão/estação
- [x] `climate/admin.py` novo (`RainfallData`, `ChirpsData`, `Projection`)
- [x] Isolamento multiusuário: `station` restrito às estações do usuário
      logado em todos os formulários
- Testado com CSV e Excel reais (datas em dois formatos diferentes,
      horário/observações opcionais, reimportação idempotente) — ver
      relatório completo em [HISTORICO.md](HISTORICO.md). Uma armadilha de
      formulário (`<input type="date">` vazio ao editar, por causa da
      localização pt-br) encontrada e corrigida — ver
      [DECISOES.md](DECISOES.md).

## Etapa 7 — Cálculo SPI (completa — 7.1, 7.2, 7.3, 7.4)

- [x] Schema `SpiResult` definido (SPI-3/6/12, classificações de seca)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `spi_spiresult`)
- [x] **7.1 Lógica de cálculo do SPI** (2026-08-23) — `spi/services.py`
      (fórmula `SPI=(Xi-X̄)/σ` do PDF, agrupada por mês do calendário,
      mínimo 10 anos de histórico por mês) + management command
      `calcular_spi` (`--scale`/`--municipio`, idempotente via
      `update_or_create`) + `spi/admin.py`. Fonte: só CHIRPS (única com
      histórico longo o bastante) — **SPI só calculável hoje em
      municípios `ativo=True`** (Tangará da Serra/Cáceres), mas o código
      é genérico (`Municipio.objects.filter(ativo=True)`, nenhum nome de
      cidade no código) e passa a funcionar em qualquer outro município
      automaticamente assim que ele tiver `ativo=True` + backfill de
      CHIRPS — zero código novo necessário. Cartão "SPI atual" adicionado
      em `farms/detalhe_fazenda.html`. Testado com dado real do usuário
      (3.246 registros, média dos z-scores ≈0, idempotência confirmada).
      Ver [DECISOES.md](DECISOES.md) sobre limiares de classificação
      (não vêm no PDF, usei os padrão McKee et al. 1993) e a decisão de
      manter `station` obrigatório por enquanto (SPI duplicado por
      estação em vez de mudar o schema).
- [x] **7.2 Validação estatística CHIRPS × local** (2026-08-23) — model
      novo `climate.ChirpsValidation` (1 resultado por estação, sempre o
      mais recente — não é série temporal), `climate/validation.py`
      (R², RMSE, MAE, MBE, índice d de Willmott, índice c de
      Camargo-Sentelhas — as 6 métricas exatas do PDF) + command
      `validar_chirps`. Compara dia a dia CHIRPS × dado local da
      estação (mínimo 3 pares). Mesma restrição de dado do SPI (só
      municípios `ativo=True` têm CHIRPS pra comparar). Cartão
      "Validação CHIRPS × Dado Local" no detalhe da fazenda. Testado
      com cenário sintético matematicamente controlado (transformação
      linear conhecida) — R²=1,000 e sinal do MBE bateram exatamente
      com o previsto. Ver [DECISOES.md](DECISOES.md) sobre as fórmulas
      e limiares de classificação (não vêm todos no PDF).
- [x] **7.3 Detecção de inconsistências** (2026-08-23) —
      `climate/quality_checks.py` (4 checagens: chuva negativa, valor
      extremo >200mm, valor repetido 3+ dias seguidos, gap de 5+ dias
      sem lançamento) + command `detectar_inconsistencias`, gravando
      via `alerts.Alert` (novo tipo `inconsistency`, reaproveita o
      model da Etapa 9 em vez de criar um novo — o PDF já fala em
      "alertas automáticos" nesta seção). Chuva negativa também
      **bloqueada na entrada** do formulário de lançamento manual, não
      só detectada depois. Idempotente (`get_or_create` por estação +
      tipo + mensagem). Cartão de alertas no detalhe da fazenda.
      Testado com cenário cobrindo as 4 checagens ao mesmo tempo — as 4
      mensagens "Possível inconsistência detectada" (texto exato do
      PDF) confirmadas. Ver [DECISOES.md](DECISOES.md) sobre os
      limiares escolhidos e por que reaproveitar `alerts.Alert`.
- [x] **7.4 Correção/calibração local do CHIRPS** (2026-08-23) —
      `climate/correction.py`: correção aditiva de viés, reaproveitando
      o MBE já calculado pela `ChirpsValidation` (Etapa 7.2) — sem
      estatística nova, sem model novo, sem command novo. `valor_corrigido
      = valor_chirps − mbe`, calculado on-the-fly (não persiste série
      corrigida, mesmo espírito "sempre o estado atual" da
      `ChirpsValidation`). Só disponível pra estação que já tenha
      validação calculada. Cartão "CHIRPS Corrigido (Calibração Local)"
      no detalhe da fazenda, últimos 10 dias, bruto × corrigido lado a
      lado. Testado com cenário sintético (viés constante conhecido de
      +10mm) — correção reproduziu o valor local original exatamente
      nos 10 dias. Ver [DECISOES.md](DECISOES.md) sobre a fórmula e por
      que a correção não realimenta o SPI (nível estação vs. nível
      município).

## Etapa 8 — Dashboards e gráficos (completa — 8.1, 8.2, 8.3)

- [x] **8.1 Estrutura do dashboard + chuva atual/acumulados + gráfico de
      série** (2026-08-23) — `dashboard/services.py` (novo:
      `chuva_atual`, `acumulados`, `serie_chuva`, tudo on-the-fly a
      partir de `RainfallData`/`ChirpsData`, sem model novo). View
      `painel` estendida (Etapa 4, mesma rota) com seletor de fazenda
      (`?fazenda=<id>`). Cartões "Chuva Atual" e "Acumulados" (7/30/90
      dias, local × CHIRPS separados). Gráfico de linha "Série de Chuva"
      com **Chart.js via CDN** (primeira lib de gráfico do projeto).
      Testado com fazenda real (só leitura) e fazenda sintética
      temporária cobrindo dado local e fallback CHIRPS — gráfico
      conferido com pixels de fato desenhados no canvas via Playwright.
      Ver [DECISOES.md](DECISOES.md).
- [x] **8.2 Tendência do SPI + comparação CHIRPS × local em gráfico**
      (2026-08-23) — `dashboard/services.py`: `serie_spi(farm)` (uma
      linha por data, colunas SPI-3/6/12, pra não desalinhar as
      escalas por causa do início tardio do SPI-12) e
      `comparacao_chirps_local(farm)` (reaproveita
      `climate.validation.pares_chirps_local`, sem estatística nova).
      Cartões "Tendência do SPI" (linha) e "Comparação CHIRPS × Dado
      Local" (dispersão com linha de referência y=x) em
      `dashboard/painel.html`, mesmo Chart.js da 8.1. Testado com
      fazenda sintética (SPI de 545 meses, comparação com R²=1,000
      conhecido) e com a fazenda real do usuário em modo leitura (119
      meses de SPI, comparação vazia — sem `ChirpsValidation` calculada
      ainda pras estações reais, tratado sem erro). Ver
      [DECISOES.md](DECISOES.md).
- [x] **8.3 Mapa geral de todas as fazendas do usuário + previsão
      climática (Open-Meteo) no dashboard** (2026-08-23) — só
      `dashboard/painel.html` mudou (sem agregação nova em
      `services.py`). Mapa Leaflet com **todas** as fazendas do
      usuário (fazenda selecionada destacada por tooltip), reaproveita
      lat/lon já presentes no `fazendas` do contexto. Previsão
      climática buscada **direto do navegador** na Open-Meteo (mesmo
      padrão client-side da Home pública, Etapa 2), card compacto
      (condição atual + 5 dias). Testado com 2 fazendas sintéticas em
      municípios diferentes (mapa com 2 marcadores, `fitBounds`
      correto) e chamada real à Open-Meteo (não mockada) retornando
      previsão válida. Ver [DECISOES.md](DECISOES.md).

**Etapa 8 (dashboard privado) está completa: 8.1, 8.2 e 8.3
concluídas.**

> A Home pública (Etapa 2) já tem cards de clima via Open-Meteo, mas isso
> não é o dashboard privado multiusuário pedido nesta etapa.

## Etapa 9 — Alertas e insights automáticos (completa — 9.1, 9.2)

- [x] Schema `Alert` (seca, excesso de chuva, risco hídrico, anomalia,
      **inconsistência** — este último tipo adicionado pela Etapa 7.3)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `alerts_alert`;
      2026-08-23 — novo tipo `inconsistency`)
- [x] `alerts/admin.py` (2026-08-23, adiantado pela Etapa 7.3)
- [x] **9.1 Alertas automáticos (seca, excesso de chuva, risco
      hídrico, anomalia climática)** (2026-08-23) — `spi/alert_checks.py`
      (novo): 4 funções, cada uma olhando o **SpiResult mais recente**
      de cada estação (condição atual, não histórico), em combinações
      diferentes de escala/severidade pra não duplicar sinal — seca
      (SPI-3), excesso de chuva (SPI-3), risco hídrico (SPI-6),
      anomalia (SPI-12, só extremos). Command
      `spi/management/commands/detectar_alertas_climaticos.py` grava
      via `alerts.Alert` (`get_or_create`, idempotente, mesmo padrão
      da 7.3). Cartão "Alertas Climáticos" em
      `farms/detalhe_fazenda.html` (separado do cartão de
      inconsistência da 7.3). Testado com estações sintéticas
      cobrindo os 4 tipos simultaneamente e contra a fazenda real do
      usuário (0 alertas — condições atuais normais/úmidas, resultado
      correto). Ver [DECISOES.md](DECISOES.md) sobre a escolha de
      escala/severidade de cada tipo.
- [x] **9.2 Insights para tomada de decisão** (2026-08-23) —
      `dashboard/insights.py` (novo): texto interpretativo baseado em
      regras sobre o SPI já calculado (sem IA/ML, decisão confirmada
      com o usuário), agrupando os itens do PDF que são a mesma
      leitura reformulada — déficit hídrico/irrigação/janela de
      plantio (SPI-3 atual), tendência de seca/pluviométrica (variação
      do SPI-3 em 3 meses), apoio à gestão hídrica (SPI-6), risco
      climático (contagem dos alertas ativos da 9.1). Reaproveita
      `spi.services.classificar_spi`, sem duplicar limiares. Cartão
      "Insights" em `dashboard/painel.html`. Testado com fazenda
      sintética cobrindo os 4 tipos de insight simultaneamente e com a
      fazenda real do usuário em modo leitura. Ver
      [DECISOES.md](DECISOES.md).
- **Pendência consciente:** notificações (email/WhatsApp) não
      implementadas — decisão explícita do usuário, confirmada por
      pergunta direta; o próprio PDF já marca esse item como "futuro",
      não como parte central da etapa. Mesmo tratamento dado à
      verificação de e-mail na Etapa 4.

**Etapa 9 (alertas e insights automáticos) está completa: 9.1 e 9.2
concluídas.**

## Etapa 10 — Projeções climáticas (completa)

- [x] Schema `Projection` definido (cenário, valor, data) — ganhou
      `unique_together = ('date', 'scenario', 'station')` na 10.2
      (`climate.0005`, precisava pra `update_or_create` idempotente)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `climate_projection`;
      2026-08-23 — `unique_together` novo)
- [x] **10.1 Análise histórica + tendência temporal** (2026-08-23) —
      `climate/trends.py` (novo): `totais_anuais(municipio)` +
      `tendencia_anual(municipio)` (regressão linear simples,
      `statistics.linear_regression` nativo do Python 3.10+, sem
      dependência nova — mesma família de `statistics.correlation` já
      usada na 7.2), mínimo 10 anos civis completos. Calculado
      on-the-fly (barato, sem persistir), exibido em cartão "Tendência
      Histórica" em `farms/detalhe_fazenda.html`. Testado contra dado
      real do usuário: Tangará da Serra, -3,5 mm/ano sobre 45 anos
      (1981-2025) — plausível e coerente com o resumo por década já
      levantado na Etapa 3.2 (década de 2020 mais seca).
- [x] **10.2 Cenários futuros (climatologia histórica)** (2026-08-23,
      mesmo dia) — `climate/trends.py`:
      `normais_climatologicas_mensais(municipio)` (média/mediana/
      percentis 25-75/mín/máx por mês do calendário, mesmo
      agrupamento "por mês, todos os anos" já usado no SPI da 7.1) +
      `cenarios_futuros(municipio, meses=6)` (3 faixas — seco/normal/
      úmido — dos percentis 25/50/75). Command
      `climate/management/commands/gerar_projecoes.py` grava em
      `climate.Projection` (model do PDF, sem uso desde a Etapa 1) por
      estação de cada município `ativo=True`, `update_or_create`
      idempotente. Cartão "Cenários Futuros" em
      `farms/detalhe_fazenda.html`, deixando explícito na UI que não é
      machine learning nem previsão de modelo climático. Testado com
      dado real (janeiro ~273mm mediana vs. julho ~9mm mediana em
      Tangará da Serra — coerente com estação seca/chuvosa da região)
      e com fazenda sintética temporária pra conferir renderização no
      navegador. Ver [DECISOES.md](DECISOES.md).
- **Confirmado com o usuário antes de codar** (pergunta direta): sem
      machine learning/IA/modelos preditivos — o PDF já marca esses
      como "Futuro", fora do escopo desta etapa.

## Etapa 11 — Exportação de dados (fora do escopo original do PDF, completa)

> Pedido do usuário depois de fechar as 10 etapas do PDF, não faz
> parte de [REQUISITOS.md](REQUISITOS.md) — mantido aqui pra registro,
> igual às outras etapas.

- [x] **Exportação Excel (.xlsx) por fazenda** (2026-08-23) —
      `farms/exports.py` (novo): `gerar_workbook_fazenda(fazenda)`
      monta um `.xlsx` com 9 abas (Fazenda, Estações, Talhões, Chuva
      Local, CHIRPS do Município, SPI, Validação CHIRPS, Alertas,
      Cenários Futuros) — dado bruto pra reanalisar em Excel/R/Python/
      SPSS fora da plataforma. Reaproveita `openpyxl` (já dependência
      desde a Etapa 6), sem lib nova. Botão "Exportar Excel" em
      `farms/detalhe_fazenda.html`. Testado com fazenda sintética
      (todas as 9 abas populadas corretamente, CHIRPS com 16.649
      linhas) e contra a fazenda real do usuário em modo leitura.
- [x] **Relatório pra imprimir/PDF** (2026-08-23, mesmo dia) — página
      standalone `farms/relatorio_fazenda.html` (não estende
      `base.html` — sem navbar/rodapé), com CSS `@media print`. O
      usuário aperta Ctrl+P e usa "Salvar como PDF" do próprio
      navegador — decisão explícita do usuário: **sem** biblioteca de
      geração de PDF no servidor (WeasyPrint foi considerado e
      descartado — exigiria libs de sistema Pango/Cairo na imagem
      Docker, dependência pesada pra um ganho pequeno frente ao
      "imprimir do navegador"). Botão "Relatório" em
      `farms/detalhe_fazenda.html`. Testado no navegador via
      Playwright — todas as seções renderizando com dado real
      (tendência, cenários, dados da fazenda).
- Refatoração: `farms/views.py` ganhou `_dados_analiticos_fazenda(fazenda)`
  — extrai as ~10 queries (SPI, validação, correção, alertas,
  tendência, cenários) que `detalhe_fazenda` e `relatorio_fazenda`
  precisam em comum, pra não duplicar a mesma "foto" analítica em duas
  views.
- Ver [DECISOES.md](DECISOES.md) sobre a escolha "imprimir do
  navegador" vs. PDF gerado no servidor.

## Etapa 12 — Manual de uso do sistema (fora do escopo original do PDF, completa)

> Pedido do usuário depois da Etapa 11. Também não faz parte de
> [REQUISITOS.md](REQUISITOS.md).

- [x] **Página de Ajuda dentro do sistema** (2026-08-23) —
      `core/views.py:ajuda` (novo, público, sem `@login_required`) +
      `core/templates/core/ajuda.html` (novo): 8 seções com índice de
      links internos — criando conta, cadastrando fazenda (mapa ou
      shapefile), talhões/estações, lançando chuva (manual/importação),
      o Painel, a página de cada fazenda (SPI/validação/alertas/
      tendência/cenários), exportação/relatório, dúvidas comuns. Rota
      `GET /ajuda/`. Linkado na navbar de `base.html` (aparece em toda
      página logada) e na navbar própria da Home (`core/index.html`,
      que não usa `base.html`). Escolhido **página dentro do sistema**
      em vez de documento separado, decisão do usuário (pergunta
      direta) — ajuda o usuário final na hora da dúvida, ao custo de
      precisar manter atualizada a cada mudança de tela. Testado no
      navegador via Playwright: link visível tanto anônimo (Home)
      quanto logado, navegação por âncora funcionando, todas as 8
      seções presentes.

## Etapa 13 — Gestão de usuários (completa parte do que a Etapa 4 do PDF deixou em aberto)

> O PDF pedia "permissões" dentro de "Cadastro de Usuários" (Etapa 4),
> mas só cadastro/login/recuperação de senha foram feitos lá — gerenciar
> OUTROS usuários (bloquear, trocar de papel) ficou faltando até o
> usuário pedir, depois de virar administrador da própria conta.

- [x] **Bloquear/desbloquear usuário + trocar perfil** (2026-08-23) —
      `accounts/views_gestao.py` (novo): `lista_usuarios`,
      `alternar_bloqueio` (`User.is_active`, com trava contra
      autobloqueio), `alterar_perfil` (`Profile.profile_type`).
      Acesso restrito a `is_superuser` ou `profile_type='admin'`.
      Rota `/painel/usuarios/` (`accounts/urls_gestao.py`, namespace
      `gestao_usuarios` — separado de `accounts/urls.py`, que só tem
      fluxos públicos de auth). Link "Gerenciar Usuários" no Painel,
      só visível pra admin. Testado com Django test client (sem
      precisar de senha real): bloqueio impede login de verdade (sem
      sessão criada), autobloqueio recusado com mensagem de erro,
      troca de perfil confirmada e revertida. Ver
      [DECISOES.md](DECISOES.md).

## Transversais (não ligadas a uma única etapa)

- [x] `makemigrations` + `migrate` para todos os apps (2026-07-16 — 6
      migrations iniciais criadas e aplicadas: accounts, farms, stations,
      climate, spi, alerts; `dashboard`/`maps`/`api`/`core` seguem sem
      migration por não terem models ainda)
- [~] `admin.py` em cada app (2026-07-16 — `maps/admin.py` e
      `accounts/admin.py` criados; `farms`, `stations`, `climate`, `spi`,
      `alerts` ainda sem)
- [~] App `api` (2026-07-16 — `api/views.py`/`api/urls.py` criados com 3
      endpoints do seletor de município, como `JsonResponse` simples, não
      DRF; ainda não há `serializers.py`/viewsets/routers DRF de fato)
- [ ] Testes automatizados (`tests.py` não existe em nenhum app)
- [ ] Manual do usuário (exigido no PDF, não encontrado no repositório)
