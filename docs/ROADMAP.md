# Roadmap — GeoClima MT

> Checklist das 10 etapas definidas em [REQUISITOS.md](REQUISITOS.md).
> `[x]` = confirmado no código nesta revisão (2026-07-16).
> `[~]` = parcial (existe algo, mas incompleto — detalhe abaixo do item).
> `[ ]` = não iniciado (nenhuma evidência encontrada no código).
> Detalhes técnicos de cada item em [ARQUITETURA.md](ARQUITETURA.md).

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
      cards "Satélite / Queimadas / Chuva Acumulada / Temperatura" são
      **links `#` sem função**
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

## Etapa 5 — Fazendas e estações

- [~] Schema `Farm` definido (nome, município, lat/lon, área, cultura,
      observações, `geom` PostGIS, `owner`)
- [~] Schema `Station` definido (tipos: Davis, Ecowitt, Ambient, IoT, manual,
      CSV; `geom` PostGIS, FKs `farm`/`owner`)
- [x] Migração aplicada ao banco (2026-07-16 — tabelas `farms_farm` e
      `stations_station`, campos `geom` POINT/SRID 4326 confirmados)
- [ ] Views/forms de cadastro de fazenda
- [ ] Views/forms de cadastro de talhão (não há model de talhão ainda)
- [ ] Views/forms de cadastro de estação
- [ ] Visualização de fazendas no mapa

## Etapa 6 — Importação CSV e dados manuais

- [~] Campo `source_type` em `RainfallData` já contempla `manual` e
      `imported_csv`
- [x] Migração aplicada ao banco (2026-07-16 — tabela `climate_rainfalldata`)
- [ ] Formulário de lançamento manual de chuva
- [ ] Importador de CSV
- [ ] Importador de Excel

## Etapa 7 — Cálculo SPI

- [~] Schema `SpiResult` definido (SPI-3/6/12, classificações de seca)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `spi_spiresult`)
- [ ] Lógica de cálculo do SPI
- [ ] Validação estatística CHIRPS × local (R², RMSE, MAE, MBE, índice d,
      índice c)
- [ ] Detecção de inconsistências (chuva negativa, extremos, duplicados,
      falhas temporais)
- [ ] Correção/calibração local do CHIRPS

## Etapa 8 — Dashboards e gráficos

- [~] App `dashboard` (2026-07-16) — não é mais um esqueleto vazio:
      `views.py`/`urls.py`/template existem, mas só como placeholder de
      login da Etapa 4 (`/painel/`, saudação + perfil). Nenhuma
      funcionalidade de dashboard de verdade ainda.
- [ ] Dashboard privado por usuário (chuva atual, acumulados, SPI,
      tendências, comparação CHIRPS × local) — vai **estender** a mesma
      view/template do `/painel/`, não criar uma rota nova (ver
      DECISOES.md)

> A Home pública (Etapa 2) já tem cards de clima via Open-Meteo, mas isso
> não é o dashboard privado multiusuário pedido nesta etapa.

## Etapa 9 — Alertas e insights automáticos

- [~] Schema `Alert` definido (seca, excesso de chuva, risco hídrico,
      anomalia)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `alerts_alert`)
- [ ] Lógica de detecção/geração automática de alertas
- [ ] Geração de insights (risco de déficit hídrico, janela de plantio,
      necessidade de irrigação etc.)
- [ ] Notificações (email/WhatsApp) — marcado como "futuro" no PDF

## Etapa 10 — Projeções climáticas

- [~] Schema `Projection` definido (cenário, valor, data)
- [x] Migração aplicada ao banco (2026-07-16 — tabela `climate_projection`)
- [ ] Lógica de tendências/cenários futuros
- [ ] Machine learning / modelos preditivos — marcado como "futuro" no PDF

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
