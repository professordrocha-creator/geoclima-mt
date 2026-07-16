# Arquitetura Atual — GeoClima MT

> Este documento descreve **apenas o que existe de fato no código** neste
> momento (revisão de 2026-07-16). Para o que ainda falta, ver
> [ROADMAP.md](ROADMAP.md). Para os requisitos originais, ver
> [REQUISITOS.md](REQUISITOS.md).

## Infraestrutura (Docker)

`docker-compose.yml` define 5 serviços:

| Serviço | Imagem/Build | Observações |
|---|---|---|
| `db` | `postgis/postgis:15-3.3-alpine` | Banco `geoclima`, porta 5432 |
| `redis` | `redis:7-alpine` | Broker/backend do Celery, porta 6379 |
| `web` | build local (`Dockerfile`) | `python manage.py runserver 0.0.0.0:8000` |
| `celery_worker` | build local (`Dockerfile`) | `celery -A geoclima worker --loglevel=info` |
| `celery_beat` | build local (`Dockerfile`) | `celery -A geoclima beat --loglevel=info --schedule=/tmp/celerybeat-schedule` (2026-07-16, Etapa 3.3) |

Não há serviço `nginx` no `docker-compose.yml`, apesar de citado nos requisitos
(ainda usando `runserver` do Django diretamente).

`celery_beat` é um serviço **separado** do `celery_worker` (não usa
`celery worker -B` embutido) — ver [DECISOES.md](DECISOES.md) sobre por
quê. O `--schedule` aponta para `/tmp` dentro do container (fora do bind
mount `.:/app`) para o arquivo de estado do agendador
(`celerybeat-schedule`) não aparecer no repositório.

`Dockerfile` instala dependências de sistema para GDAL/PostGIS
(`gdal-bin`, `libgdal-dev`, `libproj-dev`, `postgresql-client`) sobre
`python:3.11-slim`.

`requirements.txt`: Django, djangorestframework, psycopg2-binary, celery,
redis, requests, **`earthengine-api`** (adicionado em 2026-07-16, Etapa
3.1). Não há `django-leaflet`, `geopandas`, `pandas` ou bibliotecas de
importação de CSV/Excel.

## Configuração Django (`geoclima/settings.py`)

- `django.contrib.gis` habilitado, `DATABASES` usando
  `django.contrib.gis.db.backends.postgis`.
- `TIME_ZONE = 'America/Cuiaba'`, `LANGUAGE_CODE = 'pt-br'`.
- Celery configurado via `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND`
  apontando para `REDIS_URL`.
- `rest_framework` instalado em `INSTALLED_APPS`, mas nenhum app usa DRF
  ainda (nenhum `serializers.py`, `viewsets` ou router encontrado).
- `ROOT_URLCONF` registra `core.urls`, `api.urls` (sob `/api/`) e `admin/`
  (`geoclima/urls.py`).
- `GEE_PROJECT_ID` e `GEE_SERVICE_ACCOUNT_KEY_PATH` (2026-07-16, Etapa
  3.1) — lidas de variáveis de ambiente, mesmo padrão das credenciais do
  Postgres. Ver seção "Integração CHIRPS via Google Earth Engine" abaixo.

## Apps Django

Todos os 10 apps pedidos nos requisitos foram criados e estão registrados em
`INSTALLED_APPS`, mas em estágios muito diferentes de maturidade:

### `core` — único app funcional hoje
- `views.py`: view `home` (renderiza `core/templates/core/index.html`) e
  `weather_data` (stub, não usada — busca de clima migrou para o frontend).
- `core/templates/core/index.html`: página pública única do sistema.
  Consome a API pública da **Open-Meteo** (forecast + air quality)
  diretamente do JavaScript do navegador (sem passar pelo backend Django).
  Contém:
  - card de clima atual (temperatura, sensação térmica, condição, ícone);
  - grade de micro-detalhes (vento, rajada, umidade, chuva 1h/dia,
    visibilidade, pressão, índice UV, nascer/pôr do sol, AQI);
  - previsão por hora (próximas 8h) e previsão de 7 dias;
  - mapa Leaflet + tiles OpenStreetMap com geolocalização do usuário;
  - 4 cards "Mapas Agrícolas do Brasil" — **links `#` sem função real**
    (Satélite, Queimadas, Chuva Acumulada/CHIRPS, Temperatura);
  - iframe do Windy.com embutido para radar/satélite em tempo real;
  - botão que aponta para `/accounts/login/` quando deslogado, ou
    `/painel/` ("Meu Painel") quando já logado (atualizado em
    2026-07-16 — Etapa 4; antes apontava para `/admin/login/`).
- `core/weather_service.py` existe mas está **vazio**.
- `core/models.py` vazio (só comentário).

### `accounts` — auth completo desde 2026-07-16 (Etapa 4)
- `Profile` model: `OneToOneField(User)`, `profile_type` (admin, pesquisador,
  produtor, tecnico, visitante), `phone`, `created_at`. Fiel aos perfis do
  PDF.
- `accounts/signals.py`: `post_save` em `User` cria `Profile` automaticamente
  (`profile_type="produtor"` por padrão), conectado via `accounts/apps.py`
  (`ready()`).
- `accounts/forms.py`: `CadastroForm` (`UserCreationForm` + e-mail
  obrigatório/único, **sem campo de papel**) e `NovaSenhaForm`
  (`SetPasswordForm` só com classes Bootstrap).
- `accounts/views.py`: view `registrar` (FBV) — cadastra, loga
  automaticamente, redireciona pro `/painel/`.
- `accounts/urls.py` (namespace `accounts`, montado em `/accounts/`):
  `login/`, `logout/`, `registro/`, e as 4 views nativas de recuperação
  de senha do Django (`senha/recuperar/`,
  `senha/recuperar/enviado/`, `senha/redefinir/<uidb64>/<token>/`,
  `senha/redefinir/concluido/`). Login/logout/reset usam as
  `LoginView`/`LogoutView`/`PasswordReset*View` nativas do
  `django.contrib.auth`, só com `template_name` customizado — nenhuma
  view de auth foi reimplementada à mão.
- `accounts/admin.py`: `Profile` embutido (`StackedInline`) na tela do
  `User` (admin troca o papel de qualquer usuário ali mesmo) + `Profile`
  registrado avulso com busca/filtro por `profile_type`.
- `accounts/management/commands/seed_demo.py`: cria `admin_demo`
  (superusuário, perfil admin) e `joao.produtor` ("João da Silva", perfil
  produtor). Idempotente; recusa rodar com `DEBUG=False` sem `--force`.
  Credenciais em `README.md`, marcadas "somente desenvolvimento".

### `farms`
- `Farm` model (`django.contrib.gis.db.models`): `name`, `city`,
  `latitude`/`longitude` (float), `area`, `crop`, `notes`, `geom`
  (`PointField`, SRID 4326), `owner` (FK User, `on_delete=CASCADE`).
- Sem admin, views, forms, urls.

### `stations`
- `Station` model: `name`, `station_type` (davis, ecowitt, ambient, iot,
  manual, csv), `latitude`/`longitude`, `geom` (PointField), `farm` (FK
  Farm), `owner` (FK User).
- Sem admin, views, forms, urls.

### `climate`
- `RainfallData`: `date`, `value`, `source_type` (chirps, manual, station,
  imported_csv, api), FKs `station`/`farm`/`owner`,
  `unique_together = ('date', 'station', 'source_type')`. Sem lógica de
  importação ainda (Etapa 6).
- `ChirpsData` (atualizado em 2026-07-16 — Etapa 3.1): `date`, `value`,
  `latitude`/`longitude`, `geom` (PointField — hoje guarda o **centroide
  do município**, não célula-grade), FK `municipio` (`maps.Municipio`,
  nullable) + `unique_together = ('municipio', 'date')`, FKs opcionais
  `station`/`farm`/`owner` (inalteradas, sem uso ainda). Populado pelo
  command `import_chirps` (ver seção dedicada abaixo). Hoje tem **33.234
  registros** — série histórica completa 1981-01-01 a 2026-06-30 (16.617
  dias) para os 2 municípios ativos, backfill rodado em 2026-07-16 (Etapa
  3.2), 0 buracos, 0 valores negativos. Não é mais dado de teste.
- `Projection`: `date`, `scenario`, `value`, FKs `station`/`farm`/`owner`.
  Sem lógica ainda (Etapa 10).
- `climate/management/commands/import_chirps.py` — primeiro management
  command do app `climate`.

## Integração CHIRPS via Google Earth Engine (2026-07-16 — Etapa 3.1)

- **Autenticação:** conta de serviço do Google Cloud
  (`geoclima-gee-import@climatga.iam.gserviceaccount.com`), projeto
  `climatga` (Earth Engine nível Comunidade). Papéis IAM necessários na
  conta de serviço: **Earth Engine Resource Viewer**, **Earth Engine
  Resource Writer** (`earthengine.computations.create` — exigido mesmo
  para leitura agregada via `reduceRegion`) e **Service Usage Consumer**
  (`serviceusage.services.use` no projeto). Chave JSON em
  `secrets/gee-key.json` (não versionada), montada nos containers `web`
  e `celery_worker` via bind mount existente (`.:/app`) — nenhum volume
  novo precisou ser adicionado ao `docker-compose.yml`.
- **Comando:** `climate/management/commands/import_chirps.py`. Parâmetros
  `--start`/`--end` (AAAA-MM-DD, `--end` inclusive), `--municipio`
  (código IBGE, restringe a 1 município ativo), `--chunk-days` (padrão
  365 — processa períodos longos em blocos para respeitar limites do
  Earth Engine).
- **Mecanismo:** para cada `Municipio` com `ativo=True` (lido do banco,
  nunca por nome/código fixo em condicional — ver
  [DECISOES.md](DECISOES.md)), converte `municipio.geom` (já simplificado
  pelo `import_municipios`) para `ee.Geometry` e roda
  `ImageCollection('UCSB-CHG/CHIRPS/DAILY').filterDate(...).map(reduceRegion
  com Reducer.mean())`, trazendo o bloco inteiro numa única chamada
  `.getInfo()` (não uma requisição por dia). Escala de redução: 5.566 m
  (~0.05°, resolução nativa do CHIRPS).
- **Gravação:** `update_or_create` por `(municipio, date)` — idempotente
  (testado: rerun do mesmo período não duplica, só atualiza).
- **Backfill histórico completo rodado em 2026-07-16 (Etapa 3.2):**
  1981-01-01 a 2026-06-30 (última data publicada no CHIRPS — checada via
  GEE, não "hoje", para não gravar zero em dia não publicado), blocos de
  365 dias, 92 blocos (46 anos × 2 municípios), **0 erros**. Resultado:
  33.234 registros totais (16.617 por município), **0 buracos**, **0
  valores negativos**, série estável e plausível por década (relatório
  completo em [HISTORICO.md](HISTORICO.md)).
- **Atualização automática diária rodando desde 2026-07-16 (Etapa 3.3):**
  `climate/tasks.py` define `atualizar_chirps` (`@shared_task`), agendada
  em `geoclima/celery.py` (`app.conf.beat_schedule`) via
  `crontab(hour=4, minute=0)` — todo dia às 04:00 `America/Cuiaba`, no
  serviço `celery_beat` (ver acima). A task **não duplica** a lógica de
  extração: para cada município `ativo=True`, calcula
  `última_data_gravada + 1 dia` até a última data publicada no GEE, e
  chama o próprio `import_chirps` via `django.core.management.call_command`
  passando `--municipio`/`--start`/`--end`. Se não houver nada novo
  (defasagem normal do CHIRPS), loga `INFO` e segue — não é erro. Retry
  declarativo (`autoretry_for` + `retry_backoff=True`, até 5 tentativas,
  backoff exponencial até 10 min).
  - **Testado via broker real** (`celery -A geoclima call
    climate.tasks.atualizar_chirps`, não chamada Python direta): (a) no
    estado normal (ambos municípios em dia), detectou "sem dados novos"
    para os 2 em ~4,7s; (b) com os últimos 5 dias de Tangará da Serra
    apagados do banco propositalmente, reimportou exatamente esses 5 dias
    (2026-06-26 a 2026-06-30) e não tocou em Cáceres (identificado
    corretamente como sem novidade) — banco confirmado de volta a 16.617
    registros e período completo (1981-01-01 a 2026-06-30) nos dois
    municípios depois.

### `spi`
- `SpiResult`: `date`, `scale` (3/6/12), `value`, `classification`
  (extremamente_umido … seca_extrema), FKs `station`/`farm`/`owner`,
  `unique_together = ('date', 'scale', 'station')`.
- Sem lógica de cálculo do SPI.

### `alerts`
- `Alert`: `alert_type` (drought, excess_rain, water_risk, anomaly),
  `message`, `created_at`, `is_active`, FKs `station`/`farm`/`owner`.
- Sem lógica de geração/disparo de alertas.

### `maps` (atualizado em 2026-07-16 — Etapa 2.2)
- `Municipio` model (`django.contrib.gis.db.models`): `nome`, `uf` (2
  letras), `codigo_ibge` (único), `geom` (`MultiPolygonField`, SRID 4326),
  `ativo` (processamento científico habilitado), `destaque` (sugestão
  principal na Home). Tabela guarda **todos** os 5.573 municípios do
  Brasil — só Tangará da Serra (`codigo_ibge=5107958`) e Cáceres
  (`5102504`) têm `ativo=True`/`destaque=True`. Ver
  [DECISOES.md](DECISOES.md) sobre por que a plataforma é genérica por
  design.
- `maps/admin.py` — primeiro `admin.py` do projeto. Lista/filtra/busca por
  `nome`, `uf`, `codigo_ibge`.
- `maps/management/commands/import_municipios.py` — importa a malha
  municipal do IBGE (`data/ibge/BR_Municipios_2025.zip`, não versionado —
  ver `.gitignore`) direto de dentro do `.zip` via GDAL, reprojeta
  SIRGAS2000→WGS84, simplifica a geometria (~13x menor, tolerância
  configurável) e faz upsert por `codigo_ibge`. Suporta `--uf` (importar
  só um estado) e `--simplify`/`--no-simplify`. Marca Tangará da
  Serra/Cáceres como `ativo`/`destaque` ao final, por código IBGE.
- Sem views/urls próprias — os endpoints que servem `Municipio` ficam no
  app `api` (abaixo), não aqui.

### `api` (atualizado em 2026-07-16 — Etapa 2.2)
- `api/views.py` + `api/urls.py`, montado em `geoclima/urls.py` sob
  `/api/`. Views simples (`JsonResponse`, no padrão do `core`), **não**
  DRF — nenhuma dependência nova foi adicionada ao `requirements.txt`.
  - `GET /api/estados/` — UFs distintas em `maps.Municipio` + nome por
    extenso (tabela de referência fixa das 27 UFs, só para exibição).
  - `GET /api/municipios/?uf=MT` — municípios da UF: `id`, `nome`,
    `codigo_ibge`, `destaque` (sem geometria).
  - `GET /api/municipios/<id>/geojson/` — `Feature` GeoJSON do polígono
    do município + centroide nas `properties` (para o Leaflet desenhar e
    o frontend recarregar o clima sem recalcular nada).

### `dashboard` — placeholder de painel privado desde 2026-07-16 (Etapa 4)
- `models.py` continua vazio (nenhum model ainda — Etapa 8 é que vai
  precisar de algum, se for o caso).
- `dashboard/views.py`: view `painel` (`@login_required`) — busca/cria o
  `Profile` do usuário logado (rede de segurança redundante ao signal do
  `accounts`) e renderiza a saudação.
- `dashboard/urls.py` (namespace `dashboard`, montado em `/painel/`):
  uma única rota (`""`, `dashboard:painel`).
- `dashboard/templates/dashboard/painel.html`: saudação + badge do
  `profile_type`. **Isto não é o dashboard da Etapa 8** (chuva, SPI,
  gráficos, comparação CHIRPS × local) — é só a prova de que o login
  funciona; a Etapa 8 vai estender esta mesma view/template, não criar
  uma rota nova (ver [DECISOES.md](DECISOES.md)).

## Autenticação — configuração global (`geoclima/settings.py`, Etapa 4)

- `LOGIN_URL = 'accounts:login'`, `LOGIN_REDIRECT_URL = 'dashboard:painel'`,
  `LOGOUT_REDIRECT_URL = 'home'`.
- `EMAIL_BACKEND` = `django.core.mail.backends.console.EmailBackend` em
  desenvolvimento (e-mail de recuperação de senha só aparece no log do
  container `web`, não é enviado de verdade) — trocar para SMTP real
  antes de qualquer produção/beta público.
- `templates/base.html` (raiz do projeto, `TEMPLATES[0]['DIRS']`) — layout
  compartilhado (navbar/rodapé no mesmo visual da Home) usado por todas as
  páginas novas da Etapa 4 (`accounts/*`, `dashboard/painel.html`). A Home
  (`core/index.html`) **não** usa este base — continua como template
  único e autocontido, sem alteração além do link do botão de login.

## Banco de dados — estado real

**Atualizado em 2026-07-16:** `makemigrations` + `migrate` foram executados
pela primeira vez. Os 7 apps com models (`accounts`, `farms`, `stations`,
`climate`, `spi`, `alerts`, `maps`) têm `migrations/0001_initial.py`
aplicada, e as tabelas existem de fato no PostgreSQL: `accounts_profile`,
`farms_farm`, `stations_station`, `climate_rainfalldata`,
`climate_chirpsdata`, `climate_projection`, `spi_spiresult`,
`alerts_alert`, `maps_municipio`. Os campos geoespaciais (`farms_farm.geom`,
`stations_station.geom`, `climate_chirpsdata.geom`, `maps_municipio.geom`)
foram confirmados via `geometry_columns` como `POINT`/SRID 4326 (os três
primeiros) e `MULTIPOLYGON`/SRID 4326 (`maps_municipio`, 5.573 linhas —
municípios do Brasil inteiro, IBGE 2025). As FKs `owner_id`/`farm_id`/
`station_id` de isolamento multiusuário foram confirmadas em produção nas
tabelas de dado. `dashboard`, `api` e `core` continuam sem migration por
não terem models.

`maps/admin.py` é o primeiro `admin.py` do projeto (registra `Municipio`).
Os demais apps ainda não têm admin — o Django admin, para eles, só expõe
`User`/`Group` padrão. As tabelas existem no banco, mas ainda não há
views, forms nem admin usando a maioria delas (ver
[ROADMAP.md](ROADMAP.md)).

## Ausências confirmadas (busca no repositório inteiro)

- Nenhum `serializers.py` ou `tests.py` em todo o repositório
  (`accounts/forms.py` existe desde 2026-07-16, ver acima).
- Nenhum diretório `static/` (a Home usa CDNs externos para Bootstrap,
  Leaflet e Font Awesome). `templates/` na raiz do projeto existe desde
  2026-07-16 (`templates/base.html`, Etapa 4) — antes só existia o
  template único `core/templates/core/index.html`.

> Atualizado em 2026-07-16: o projeto já tem `management/commands/` em
> dois apps (`maps/import_municipios`, `climate/import_chirps`), já tem
> integração com Google Earth Engine (`earthengine-api`) e já tem uma
> `tasks.py` real com task agendada (`climate/tasks.py`,
> `atualizar_chirps`, serviço `celery_beat`) — esses itens saíram da
> lista de ausências.
