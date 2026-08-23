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
redis, requests, `earthengine-api` (2026-07-16, Etapa 3.1),
**`openpyxl`** (2026-08-23, Etapa 6 — leitura de `.xlsx`). Não há
`django-leaflet`, `geopandas` ou `pandas`. CSV é lido só com a lib
padrão do Python (`csv`), sem dependência nova.

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
- `views.py`: view `home` (renderiza `core/templates/core/index.html`),
  `weather_data` (stub, não usada — busca de clima migrou para o frontend),
  e `ajuda` (novo, 2026-08-23 — Etapa 12, ver abaixo).
- `core/templates/core/index.html`: página pública única do sistema.
  Consome a API pública da **Open-Meteo** (forecast + air quality)
  diretamente do JavaScript do navegador (sem passar pelo backend Django).
  Contém:
  - card de clima atual (temperatura, sensação térmica, condição, ícone);
  - grade de micro-detalhes (vento, rajada, umidade, chuva 1h/dia,
    visibilidade, pressão, índice UV, nascer/pôr do sol, AQI);
  - previsão por hora (próximas 8h) e previsão de 7 dias;
  - mapa Leaflet + tiles OpenStreetMap com geolocalização do usuário;
  - iframe do Windy.com embutido para radar/satélite em tempo real;
  - botão que aponta para `/accounts/login/` quando deslogado, ou
    `/painel/` ("Meu Painel") quando já logado (atualizado em
    2026-07-16 — Etapa 4; antes apontava para `/admin/login/`).
- `core/weather_service.py` existe mas está **vazio**.
- `core/models.py` vazio (só comentário).
- **Removido em 2026-08-23:** os 4 cards "Mapas Agrícolas do Brasil"
  (Satélite, Queimadas, Chuva Acumulada/CHIRPS, Temperatura) — eram
  `<a href="#">` sem função real desde sempre (nunca vieram
  funcionais). Removido o bloco HTML e o CSS específico
  (`.agricultural-map-card` e classes filhas) a pedido do usuário, em
  vez de manter um placeholder inacabado na Home pública.
- **`core/templates/core/ajuda.html`** (novo, 2026-08-23 — Etapa 12,
  fora do escopo original do PDF, pedido do usuário): manual de uso do
  sistema, público (`GET /ajuda/`, sem `@login_required` — ajuda quem
  ainda não tem conta a decidir se cadastra). Estende `base.html`
  (mesmo layout de `accounts`/`dashboard`), **não** o template
  standalone da Home. 8 seções com âncoras (conta, fazenda, talhões/
  estações, chuva, painel, página da fazenda, exportação, dúvidas
  comuns), índice no topo com links internos. Linkado em dois lugares:
  navbar de `base.html` (`{% block navbar_extra %}`, aparece em toda
  página que estende esse layout) e navbar própria de `core/index.html`
  (a Home não usa `base.html` — precisou de um link manual separado).

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
- **Gestão de usuários (2026-08-23 — Etapa 13, fora do escopo original
  do PDF; pedido do usuário depois de virar administrador da própria
  conta):** `accounts/views_gestao.py` (novo) — `lista_usuarios`
  (tabela com todos os usuários, perfil, status ativo/bloqueado, data
  de cadastro), `alternar_bloqueio` (toggle `User.is_active`, bloqueia
  login sem apagar nada; usuário não pode bloquear a própria conta) e
  `alterar_perfil` (troca `Profile.profile_type` de qualquer usuário,
  sem precisar do `/admin/` do Django). Acesso restrito a
  `is_superuser` **ou** `Profile.profile_type == 'admin'`
  (`@user_passes_test`, redireciona pro painel se não for admin).
  `accounts/urls_gestao.py` (novo, `app_name="gestao_usuarios"`,
  **não** o mesmo `accounts/urls.py` — este é montado em
  `/painel/usuarios/`, convenção de URL da área privada, enquanto
  `accounts/urls.py` fica em `/accounts/`, só fluxos públicos de
  auth). Template `accounts/templates/accounts/lista_usuarios.html`.
  Link "Gerenciar Usuários" em `dashboard/painel.html`, só visível pra
  quem é admin. Testado com Django test client (`force_login`, sem
  precisar da senha real do usuário promovido a admin nesta sessão):
  bloqueio/desbloqueio, troca de perfil, bloqueio da própria conta
  corretamente recusado, e um usuário bloqueado de fato **não
  consegue logar** (sem `_auth_user_id` na sessão) — testado de
  verdade, não só que o campo mudou no banco.

### `farms` — CRUD completo desde 2026-08-23 (Etapa 5)
- `Farm` model: `name`, `city` (texto livre legado, sem uso no form),
  `municipio` (FK `maps.Municipio`, `on_delete=PROTECT` — ver
  [DECISOES.md](DECISOES.md)), `latitude`/`longitude` (float), `area`,
  `crop`, `notes`, `geom` (`PointField`, SRID 4326), `owner` (FK User,
  `CASCADE`).
- `Talhao` model (novo): `name`, `area`, `crop`, `latitude`/`longitude`,
  `geom` (`PointField`), FKs `farm`/`owner` (`CASCADE`).
- `farms/forms.py`: `FarmForm` (município via seletor Estado→Cidade da
  Home, lat/lon via clique no mapa — não são digitados) e `TalhaoForm`
  (mesmo padrão de mapa, sem seletor de município — herda o da fazenda).
- `farms/views.py`: FBVs `lista_fazendas`, `criar_fazenda`,
  `editar_fazenda`, `excluir_fazenda`, `detalhe_fazenda`, `criar_talhao`,
  `editar_talhao`, `excluir_talhao`. Todas `@login_required` e todo
  acesso a um objeto existente busca com `owner=request.user` **na
  própria query** (nunca filtra depois de já ter o objeto).
- `farms/urls.py` (namespace `farms`, montado em `/painel/fazendas/`).
- `farms/admin.py`: `Farm` com `Talhao` inline, `autocomplete_fields`
  para `municipio`.
- Templates (`farms/templates/farms/`): `lista_fazendas.html` (mapa com
  todas as fazendas do usuário), `form_fazenda.html` (Estado→Cidade +
  mapa clicável + upload de shapefile), `detalhe_fazenda.html` (mapa da
  sede + talhões + estações + contorno importado, quando existe),
  `form_talhao.html`, `confirmar_exclusao.html`.

**Importação de Shapefile (2026-08-23):** `Farm.poligono`
(`MultiPolygonField`, opcional) — contorno da propriedade, preenchido
ao importar um `.zip` no formulário de fazenda (campo `shapefile`,
`farms/forms.py`, não é campo do model). `farms/shapefile_import.py`
extrai o zip, lê todos os `.shp` encontrados via GDAL
(`django.contrib.gis.gdal.DataSource`), reprojeta pro WGS84 usando o
`.prj` de cada um, une feições de polígono num `MultiPolygon` só, e
devolve pontos como uma lista simples. `farms/views.py`
(`criar_fazenda`/`editar_fazenda`) usa o centroide do polígono como
`geom`/`latitude`/`longitude` quando há shapefile com polígono (manda
mais que o clique manual no mapa), e cria uma `Station` por ponto
encontrado (tipo "manual", nome da coluna de atributo do shapefile se
existir). Endpoint `GET /painel/fazendas/<id>/poligono.json`
(`farms:poligono_fazenda_json`, restrito ao dono) serve o contorno em
GeoJSON pro mapa de cadastro de estação desenhar como referência.

**Exportação de dados (2026-08-23 — Etapa 11, fora do escopo original
do PDF, pedido do usuário):**
- **`farms/exports.py`** (novo): `gerar_workbook_fazenda(fazenda)`
  monta um `openpyxl.Workbook` com 9 abas — Fazenda, Estações,
  Talhões, Chuva Local (`RainfallData` exceto `source_type='chirps'`),
  CHIRPS do Município (`ChirpsData` completo, pode ter dezenas de
  milhares de linhas), SPI, Validação CHIRPS, Alertas, Cenários
  Futuros. Cada aba é dado "cru" (uma linha por registro), pra
  reanalisar em Excel/R/Python/SPSS fora da plataforma — não é um
  resumo visual. `farms/views.py:exportar_fazenda_excel` serve como
  download (`Content-Disposition: attachment`), rota
  `GET /painel/fazendas/<id>/exportar.xlsx`.
- **`farms/templates/farms/relatorio_fazenda.html`** (novo): página
  **standalone** (não estende `base.html` — sem navbar/rodapé), pronta
  pra impressão (`@media print` esconde o botão de imprimir e evita
  quebra de página no meio de tabela/seção). Botão "Imprimir/Salvar
  como PDF" chama `window.print()` — o "PDF" é o recurso nativo do
  navegador (Ctrl+P → Salvar como PDF), **não** é gerado no servidor
  (decisão explícita do usuário, ver [DECISOES.md](DECISOES.md) sobre
  por que não WeasyPrint). `farms/views.py:relatorio_fazenda` serve a
  rota `GET /painel/fazendas/<id>/relatorio/`.
- **`farms/views.py:_dados_analiticos_fazenda(fazenda)`** (novo
  helper): extrai as ~10 queries (SPI, validação CHIRPS, correção,
  alertas, tendência, cenários) que `detalhe_fazenda` e
  `relatorio_fazenda` precisam em comum — evita duplicar a mesma
  "foto" analítica da fazenda em duas views. `detalhe_fazenda` foi
  refatorada pra usar esse helper (comportamento idêntico, sem
  mudança visual).
- Botões "Relatório" e "Exportar Excel" em
  `farms/detalhe_fazenda.html`, ao lado de "Editar"/"Excluir".
- Testado com fazenda sintética (9 abas do Excel populadas
  corretamente, CHIRPS com 16.649 linhas; relatório renderizando todas
  as seções) e contra a fazenda real do usuário em modo leitura
  (`gerar_workbook_fazenda`/`_dados_analiticos_fazenda` chamados
  direto no shell, sem escrita).

### `stations` — CRUD completo desde 2026-08-23 (Etapa 5)
- `Station` model (inalterado): `name`, `station_type` (davis, ecowitt,
  ambient, iot, manual, csv), `latitude`/`longitude`, `geom`
  (PointField), `farm` (FK Farm), `owner` (FK User).
- `stations/forms.py`: `StationForm` — exige `user=` no construtor para
  restringir o `<select>` de fazenda às do próprio usuário.
- `stations/views.py`: FBVs `lista_estacoes`, `criar_estacao`,
  `editar_estacao`, `excluir_estacao`, todas `@login_required` +
  filtradas por `owner`.
- `stations/urls.py` (namespace `stations`, montado em
  `/painel/estacoes/`).
- `stations/admin.py`.
- Templates (`stations/templates/stations/`): `lista_estacoes.html`,
  `form_estacao.html` (mapa recentraliza ao trocar a fazenda escolhida),
  `confirmar_exclusao.html`.

**Padrão de mapa "clique para marcar" (Etapa 5):** os três formulários
(fazenda, talhão, estação) usam Leaflet com um marcador arrastável —
clicar no mapa ou arrastar o marcador preenche `latitude`/`longitude`
(campos escondidos, `class="d-none"`) via JS; nada de coordenadas
digitadas à mão. Como esses templates embutem valores `FloatField` do
Django dentro de `<script>`, todos usam `{% load l10n %}` +
`{% localize off %}` para evitar que o Django formate os números com
vírgula decimal (padrão `pt-br`) e quebre a sintaxe JavaScript — ver
[DECISOES.md](DECISOES.md), é uma armadilha fácil de reintroduzir em
templates novos.

### `climate` — CRUD de lançamento/importação de chuva desde 2026-08-23 (Etapa 6)
- `RainfallData` (atualizado 2026-08-23): `date`, `time` (novo, opcional),
  `value`, `notes` (novo, opcional), `source_type` (chirps, manual,
  station, imported_csv, api), FKs `station`/`farm`/`owner`,
  `unique_together = ('date', 'station', 'source_type')`.
- `climate/forms.py`: `LancamentoManualForm` (`station` restrito ao
  usuário, `date`/`time` com `format=` explícito nos widgets — ver
  [DECISOES.md](DECISOES.md) sobre por que) e `ImportacaoArquivoForm`
  (upload `.csv`/`.xlsx`).
- `climate/data_import.py`: parser único pra CSV e Excel — detecta
  colunas pelo nome do cabeçalho (`data`/`date`,
  `valor`/`chuva`/`precipitacao`, `horario`, `observacoes`), datas em
  `AAAA-MM-DD` ou `DD/MM/AAAA`. Usa `openpyxl` (dependência nova,
  `requirements.txt`) pro `.xlsx`; CSV usa só a lib padrão do Python.
- `climate/views.py`: `lista_lancamentos`, `criar_lancamento`,
  `editar_lancamento`, `excluir_lancamento`, `importar_arquivo` — todas
  `@login_required`, gravação por `update_or_create(station, date,
  source_type)` (idempotente, sem duplicar).
- `climate/urls.py` (namespace `climate`, montado em `/painel/chuva/`).
- `climate/admin.py`: `RainfallData`, `ChirpsData`, `ChirpsValidation`,
  `Projection`.
- **`ChirpsValidation`** (novo, Etapa 7.2): `OneToOneField(Station)` —
  1 resultado por estação, sempre o mais recente (não série temporal).
  `n_pares`, `r2`, `rmse`, `mae`, `mbe`, `indice_d`, `indice_c`,
  `desempenho_c` (choices). `climate/validation.py` calcula (compara
  `RainfallData` local × `ChirpsData` do município, dia a dia, mínimo 3
  pares) e `climate/management/commands/validar_chirps.py` grava via
  `update_or_create`. Exibido em `farms/detalhe_fazenda.html`. Ver
  [DECISOES.md](DECISOES.md) pras fórmulas (Willmott/Camargo-Sentelhas).
- **`climate/quality_checks.py`** (novo, Etapa 7.3): 4 funções de
  detecção sobre `RainfallData` local — chuva negativa, valor extremo
  (>200mm), valor repetido 3+ dias seguidos, gap de 5+ dias sem
  lançamento. `climate/management/commands/detectar_inconsistencias.py`
  roda as 4 e grava em `alerts.Alert` (tipo `inconsistency`, novo — ver
  seção `alerts` acima). `LancamentoManualForm.clean_value` também
  bloqueia chuva negativa direto no formulário (não só detecta depois).
- **`climate/correction.py`** (novo, Etapa 7.4): correção/calibração
  local do CHIRPS — `corrigir_valor(valor_chirps, mbe) = valor_chirps −
  mbe` (reaproveita o MBE já calculado pela `ChirpsValidation` da
  Etapa 7.2, sem estatística nova) e `serie_chirps_corrigida(station,
  dias=10)`, que devolve os últimos N dias de `ChirpsData` do
  município, bruto × corrigido lado a lado. Sem model e sem management
  command novos — tudo calculado on-the-fly a partir do `ChirpsData`
  bruto (intocado) e do MBE mais recente, só disponível pra estação que
  já tenha `ChirpsValidation`. Exibido em `farms/detalhe_fazenda.html`
  ("CHIRPS Corrigido (Calibração Local)"). Ver [DECISOES.md](DECISOES.md).
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
  **Etapa 10.2 (2026-08-23):** ganhou `unique_together = ('date',
  'scenario', 'station')` (`climate.0005`, pra `update_or_create`
  idempotente — 1 fazenda pode ter 3 linhas no mesmo `date`, uma por
  `scenario`). Populado por `gerar_projecoes` (ver abaixo).
- **`climate/trends.py`** (novo, Etapa 10): análise histórica,
  tendência temporal e cenários futuros do CHIRPS — **sem machine
  learning** (o PDF marca ML/IA/modelos preditivos explicitamente como
  "Futuro"; decisão de interpretação confirmada com o usuário antes de
  codar). `tendencia_anual(municipio)` — regressão linear simples
  (`statistics.linear_regression`, nativo do Python 3.10+, sem
  dependência nova) sobre os totais anuais, mínimo 10 anos civis
  completos. `normais_climatologicas_mensais(municipio)` — média/
  mediana/percentis 25-75/mín/máx por mês do calendário, mesmo
  agrupamento "por mês, todos os anos" já usado no SPI (7.1).
  `cenarios_futuros(municipio, meses=6)` — 3 faixas (seco/normal/
  úmido = percentis 25/50/75) pros próximos meses. Tendência é
  calculada **on-the-fly** (barata, mesmo espírito de
  `climate/correction.py`); cenários são **persistidos** em
  `Projection` via `climate/management/commands/gerar_projecoes.py`
  (itera município `ativo=True` → estação, `update_or_create`,
  mesmo padrão "rode o comando" já usado em SPI/validação/alertas —
  sem agendamento automático ainda, só o CHIRPS em si roda sozinho via
  Celery Beat). Cartões "Tendência Histórica" e "Cenários Futuros" em
  `farms/detalhe_fazenda.html`, com aviso explícito de que não é
  previsão de modelo climático nem machine learning. Testado com dado
  real (Tangará da Serra: -3,5 mm/ano de tendência sobre 45 anos;
  janeiro ~273mm mediana vs. julho ~9mm mediana — coerente com a
  sazonalidade da região) e fazenda sintética temporária pra conferir
  renderização no navegador. Ver [DECISOES.md](DECISOES.md).

**Etapa 10 (projeções climáticas) está completa.**
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

### `spi` — cálculo funcionando desde 2026-08-23 (Etapa 7.1)
- `SpiResult`: `date`, `scale` (3/6/12), `value`, `classification`
  (extremamente_umido … seca_extrema), FKs `station`/`farm`/`owner`,
  `unique_together = ('date', 'scale', 'station')`. Model inalterado
  nesta etapa (sem migration nova).
- `spi/services.py`: `calcular_serie_spi(municipio, escala)` — agrega
  `climate.ChirpsData` (diário) em totais mensais, monta somas móveis
  de 3/6/12 meses, padroniza (z-score) cada uma contra a distribuição
  do mesmo mês do calendário em todos os anos (mínimo 10 anos de
  histórico), classifica em 6 categorias (limiares McKee et al. 1993 —
  não vêm no PDF, ver [DECISOES.md](DECISOES.md)).
- `spi/management/commands/calcular_spi.py`: `--scale`/`--municipio`,
  itera `maps.Municipio.objects.filter(ativo=True)` (nenhum nome de
  cidade no código) e grava um `SpiResult` por estação de cada fazenda
  do município, via `update_or_create` (idempotente).
- `spi/admin.py` (novo).
- **Só funciona hoje pra municípios `ativo=True`** (Tangará da
  Serra/Cáceres) — não é limitação de código, é porque só esses têm
  CHIRPS importado (Etapa 3). Testado com dado real do usuário: 3.246
  registros, média dos z-scores ≈0 em todas as escalas, idempotência
  confirmada.
- Exibido como um cartão "SPI atual" (3 valores mais recentes,
  SPI-3/6/12) em `farms/detalhe_fazenda.html`, e como gráfico de
  tendência no dashboard privado (Etapa 8.2, `dashboard/services.py`).
- **`spi/alert_checks.py`** (novo, Etapa 9.1): 4 funções de detecção
  de alerta climático a partir do **SpiResult mais recente de cada
  estação** (não histórico — é sobre a condição atual), cada uma numa
  combinação diferente de escala/severidade pra não duplicar sinal:
  seca (SPI-3 em seca_moderada+), excesso de chuva (SPI-3 em
  muito_umido+), risco hídrico (SPI-6 em seca_severa+), anomalia
  climática (SPI-12 nos extremos). Ver [DECISOES.md](DECISOES.md) pro
  raciocínio de cada escolha de escala.
  `spi/management/commands/detectar_alertas_climaticos.py` roda as 4 e
  grava em `alerts.Alert` (`get_or_create` por station+tipo+mensagem,
  idempotente — mesmo padrão da Etapa 7.3).

### `alerts` — usado desde 2026-08-23 pelas Etapas 7.3 e 9.1
- `Alert`: `alert_type` (drought, excess_rain, water_risk, anomaly,
  inconsistency — `alerts.0002`), `message`, `created_at`,
  `is_active`, FKs `station`/`farm`/`owner`.
- `alerts/admin.py` (novo, Etapa 7.3).
- **Todos os 5 tipos têm lógica de geração agora**: `inconsistency` via
  `climate/quality_checks.py` (Etapa 7.3, sobre qualidade do DADO
  local); `drought`/`excess_rain`/`water_risk`/`anomaly` via
  `spi/alert_checks.py` (Etapa 9.1, sobre o CLIMA em si, a partir do
  SPI). Exibidos em dois cartões separados em
  `farms/detalhe_fazenda.html` ("Possíveis Inconsistências no Dado
  Local" e "Alertas Climáticos") — tipos diferentes, cartões
  diferentes, para não confundir problema de dado com condição
  climática real.

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

### `dashboard` — dashboard privado em construção (Etapa 8, sub-etapas)
- `models.py` continua vazio — as agregações da Etapa 8.1 são todas
  calculadas on-the-fly a partir de `climate.RainfallData`/`ChirpsData`
  (nenhum model novo precisou, mesmo espírito de `climate/correction.py`
  na 7.4).
- **`dashboard/services.py`** (novo, Etapa 8.1): `chuva_atual(farm)`
  (valor mais recente, prioriza dado local, cai pro CHIRPS do
  município se não houver lançamento local), `acumulados(farm)` (total
  em mm nas janelas 7/30/90 dias, local e CHIRPS separados — nunca
  somados juntos, pra não misturar medição com estimativa), e
  `serie_chuva(farm, dias=90)` (série diária local × CHIRPS lado a
  lado, pro gráfico). Tudo agregado por **fazenda** (soma todas as
  estações dela), não por estação individual.
- `dashboard/views.py`: view `painel` (`@login_required`) — busca/cria o
  `Profile` do usuário logado, monta a lista de fazendas do usuário e,
  se houver ao menos uma, um seletor (`?fazenda=<id>`, padrão a
  primeira) com as agregações de `services.py` da fazenda escolhida.
  Mesma view/rota da Etapa 4 **estendida**, não uma rota nova (decisão
  já tomada na Etapa 4, ver [DECISOES.md](DECISOES.md)).
- `dashboard/urls.py` (namespace `dashboard`, montado em `/painel/`):
  inalterado, uma única rota (`""`, `dashboard:painel`).
- `dashboard/templates/dashboard/painel.html`: saudação + badge do
  `profile_type` + links rápidos (inalterados desde a Etapa 5), mais
  (Etapa 8.1): seletor de fazenda, cartão "Chuva Atual", cartão
  "Acumulados" (7/30/90 dias), gráfico de linha "Série de Chuva"
  (**Chart.js 4.4.4 via CDN** — primeira lib de gráfico do projeto,
  mesmo padrão de carregamento do Leaflet, sem dependência Python
  nova). Sem fazenda cadastrada, mostra call-to-action pra cadastrar
  uma, em vez do dashboard vazio.
- Testado com fazenda real do usuário (`daniel`, id=8) só em leitura
  (`dashboard/services.py` direto no shell, sem `.delete()`/escrita) e
  com fazenda sintética temporária (`joao.produtor`, removida depois,
  filtrada por owner) cobrindo os dois casos: dado local recente
  (`chuva_atual` origem "local") e fallback pro CHIRPS quando não há
  lançamento numa janela. Gráfico conferido renderizado de fato
  (pixels desenhados no `<canvas>`, não só "sem erro de JS") via
  Playwright.
- **Etapa 8.2 (2026-08-23):** duas funções novas em
  `dashboard/services.py`. `serie_spi(farm, anos=10)` — histórico de
  SPI-3/6/12 da fazenda (usa a 1ª estação da fazenda como
  representante, já que o valor é o mesmo pra todas as estações do
  município — ver Etapa 7.1). Devolve **uma linha por data** com as 3
  escalas como colunas (`spi_3`/`spi_6`/`spi_12`, `None` quando a
  escala ainda não tem valor pra aquela data), não uma lista por
  escala — SPI-12 só começa bem depois de SPI-3 (precisa de 12 meses
  de janela móvel), então alinhar por índice de array em vez de por
  data desalinharia o gráfico; o formato "uma linha por data" evita
  esse erro por construção. `comparacao_chirps_local(farm)` — pares
  (CHIRPS, local) de cada estação já validada da fazenda (reaproveita
  `climate.validation.pares_chirps_local`, sem recalcular nada), pro
  gráfico de dispersão que acompanha visualmente o cartão de métricas
  numéricas da Etapa 7.2.
- **`dashboard/painel.html` (Etapa 8.2):** dois cartões novos —
  "Tendência do SPI" (linha, 3 séries SPI-3/6/12, `spanGaps: true`
  no Chart.js pra lidar com o início tardio do SPI-12 sem quebrar a
  linha) e "Comparação CHIRPS × Dado Local" (dispersão — eixo X
  CHIRPS, eixo Y local, uma cor por estação, mais uma linha diagonal
  de referência "concordância perfeita" y=x). Mesmo Chart.js já
  carregado na 8.1, sem lib nova.
- **Etapa 8.3 (2026-08-23) — Etapa 8 completa:** só `dashboard/painel.html`
  mudou, sem tocar `views.py`/`services.py` (não precisou de agregação
  nova — mapa usa lat/lon que já vêm no `fazendas` do contexto,
  previsão é fetch puramente client-side). Dois itens:
  - **Mapa geral** ("Mapa das Minhas Fazendas"): Leaflet mostrando
    **todas** as fazendas do usuário (não só a selecionada no
    seletor), com a fazenda ativa destacada por um tooltip fixo. Mesmo
    padrão de carregamento do Leaflet já usado em
    `farms/detalhe_fazenda.html` (CDN `unpkg.com`).
  - **Previsão climática**: reaproveita a Open-Meteo (mesma API da
    Home pública, Etapa 2), buscada **direto do navegador** — não
    passa pelo backend Django, mesmo padrão da Home. Card compacto
    (condição atual + 5 dias), com um `CODIGOS_TEMPO` reduzido
    (subconjunto do mapeamento completo de `core/index.html` — a
    versão cheia continua só na Home).
  - Testado com fazenda sintética temporária com 2 fazendas em
    municípios diferentes (Tangará da Serra/Cáceres) — mapa mostrando
    2 marcadores corretamente, `fitBounds` cobrindo as duas; previsão
    real da Open-Meteo carregada com sucesso (chamada de rede real,
    não mockada). Sem erros de console.
  - **Etapa 8 (dashboard privado) está completa: 8.1, 8.2 e 8.3
    concluídas.**
- **Etapa 9.2 (2026-08-23):** `dashboard/insights.py` (novo) —
  `gerar_insights(dados_spi, alertas_climaticos)` interpreta, por
  REGRA (sem IA/ML, decisão confirmada com o usuário), o SPI-3/6 mais
  recente (reaproveita `dados_spi` da 8.2) e os alertas climáticos já
  filtrados pela view (reaproveita a lista da 9.1, não reconsulta).
  Cobre os itens do PDF ("Insights para Tomada de Decisão") agrupando
  os que são a mesma leitura reformulada: déficit hídrico/necessidade
  de irrigação/janela de plantio (um único insight, do SPI-3 atual),
  tendência de seca/pluviométrica (um insight, variação do SPI-3 nos
  últimos 3 meses), apoio à gestão hídrica (SPI-6, só aparece se houver
  déficit de médio prazo), risco climático (contagem dos alertas
  ativos da 9.1). Reaproveita `spi.services.classificar_spi` — não
  duplica os limiares de classificação. `dashboard/views.py` monta
  `alertas_climaticos` (mesmo filtro usado em
  `farms/views.py:detalhe_fazenda`) e chama `gerar_insights`. Cartão
  "Insights" em `dashboard/painel.html`, logo depois do seletor de
  fazenda. Testado com fazenda sintética cobrindo os 4 tipos de
  insight simultaneamente (seca + tendência de piora + gestão hídrica
  + risco climático) e com a fazenda real do usuário em modo leitura
  (2 insights corretos: condição normal + tendência de piora). **Etapa
  9 (alertas e insights) está completa: 9.1 e 9.2 concluídas**
  (notificações email/WhatsApp confirmadas fora do escopo, ver
  [DECISOES.md](DECISOES.md)).

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

`maps/admin.py` foi o primeiro `admin.py` do projeto; todos os apps
com model (`accounts`, `farms`, `stations`, `climate`, `spi`,
`alerts`) têm admin próprio hoje (`alerts/admin.py` desde a Etapa 7.3).
**Atualizado em 2026-08-23 (Etapa 5):** migration `farms.0002` alterou
`farms_farm` (nova coluna `municipio_id`, FK para `maps_municipio`,
`city` virou nullable) e criou `farms_talhao`; `farms.0003` adicionou
`farms_farm.poligono` (`MultiPolygonField`, importação de shapefile).
**Etapa 6 (mesmo dia):** `climate.0003` acrescentou `time`/`notes` a
`RainfallData`. **Etapa 7.1 (mesmo dia, sem migration nova):**
`spi_spiresult` passou a ser preenchida de verdade pelo `calcular_spi`.
**Etapa 7.3:** `alerts.0002` adicionou o tipo `inconsistency`.
**Etapa 10.2:** `climate.0005` adicionou `unique_together` a
`Projection`. Todas as tabelas do projeto (`farms_farm`/
`stations_station`/`farms_talhao`/`climate_rainfalldata`/
`spi_spiresult`/`alerts_alert`/`climate_projection`) têm lógica de
verdade por trás agora — nenhuma continua "schema sem uso" (ver
[ROADMAP.md](ROADMAP.md), todas as Etapas 1-10 completas).

## Ausências confirmadas (busca no repositório inteiro)

- Nenhum `serializers.py` ou `tests.py` em todo o repositório
  (`forms.py` existe em `accounts`, `farms` e `stations`, ver acima).
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
