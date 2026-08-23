# Relatório Técnico — GeoClima MT

> Documento de base para a escrita da dissertação de mestrado. Compilado
> a partir de `CLAUDE.md`, `docs/REQUISITOS.md`, `docs/ROADMAP.md`,
> `docs/HISTORICO.md`, `docs/ARQUITETURA.md`, `docs/DECISOES.md`,
> `README.md`, `requirements.txt`, `Dockerfile` e `docker-compose.yml`.
> Data de compilação: 2026-08-23. Nenhuma informação aqui foi inferida
> além do que está documentado ou presente no código do repositório.

---

## 1. Visão geral do sistema

### 1.1 Origem e nome

O documento de requisitos original ("PROMPT MASTER COMPLETO — GeoClima
MT (Geotecnologia e Clima para Mato Grosso)") refere-se ao sistema
proposto como **ACTS (AgroClima Tangará da Serra)**. O repositório real
do projeto foi nomeado **GeoClima MT**, nome adotado em toda a
documentação técnica subsequente.

### 1.2 Objetivo da plataforma

Conforme `docs/REQUISITOS.md`, o sistema tem como objetivo constituir
uma **plataforma climática inteligente** para Mato Grosso, cobrindo:

- monitoramento de precipitação;
- cálculo de secas;
- análise climática;
- integração de dados locais;
- apoio à tomada de decisão agrícola;
- gestão hídrica;
- projeção de cenários climáticos.

O sistema é dividido em duas áreas: uma **área pública** (sem login,
funcionando como portal climático de Mato Grosso, com informações em
tempo real) e uma **área privada multiusuário** (cadastro de fazendas,
estações, análises e alertas, isolados por usuário).

### 1.3 Problema que resolve

A pesquisa de mestrado por trás do projeto valida dados de precipitação
estimados por satélite (CHIRPS) para dois municípios de Mato Grosso —
**Tangará da Serra** e **Cáceres** — comparando-os com dado medido
localmente. O sistema resolve, de forma integrada, três problemas
conexos:

1. **Acesso a dado histórico de precipitação confiável**, sem exigir
   que o usuário baixe e processe arquivos raster brutos — resolvido
   via integração com o Google Earth Engine (GEE).
2. **Validação e calibração local do dado de satélite** — o sistema
   compara CHIRPS com o que o produtor efetivamente mede em campo,
   calculando métricas estatísticas padronizadas (R², RMSE, MAE, MBE,
   índices d e c) e aplicando uma correção de viés.
3. **Interpretação do dado para apoio à decisão agrícola** — cálculo do
   Índice de Precipitação Padronizada (SPI), geração de alertas
   climáticos automáticos e insights textuais descritivos, sem
   depender de avaliação manual de séries históricas brutas.

### 1.4 Público-alvo

- **Área pública:** qualquer visitante, sem necessidade de cadastro —
  portal climático com dados em tempo real (Open-Meteo) e mapa
  interativo.
- **Área privada multiusuário:** produtores rurais, pesquisadores,
  técnicos e administradores. `docs/REQUISITOS.md` define 5 perfis de
  usuário: **administrador, pesquisador, produtor, técnico,
  visitante** (implementados em `accounts.Profile.profile_type`). Cada
  usuário só acessa seus próprios dados (fazendas, estações, análises,
  alertas) — isolamento multiusuário reforçado em toda tabela de dado
  do sistema.

---

## 2. Arquitetura técnica

### 2.1 Stack completa

| Camada | Tecnologia | Observação |
|---|---|---|
| Backend | Django >=4.2,<5.0 | Framework principal |
| API (instalada, não usada) | Django REST Framework >=3.14.0 | `rest_framework` está em `INSTALLED_APPS`, mas nenhum app usa DRF ainda — os endpoints existentes (`api/`) são `JsonResponse` simples |
| Banco de dados | PostgreSQL + PostGIS 15-3.3 (`postgis/postgis:15-3.3-alpine`) | Suporte geoespacial via `django.contrib.gis` |
| Driver do banco | psycopg2-binary >=2.9.6 | |
| Containerização | Docker / Docker Compose | 5 serviços (ver seção 9) |
| Fila/agendamento | Celery >=5.3.1 + Redis >=4.6.0 | Worker + Beat separados |
| Mapas | Leaflet + OpenStreetMap | Via CDN, sem dependência Python |
| Dado de precipitação regional | CHIRPS (`UCSB-CHG/CHIRPS/DAILY`) | Acessado via Google Earth Engine |
| Acesso ao GEE | `earthengine-api` >=1.0.0 | Autenticação via conta de serviço |
| Requisições HTTP | `requests` >=2.31.0 | |
| Planilhas | `openpyxl` >=3.1.0 | Leitura de `.xlsx` (Etapa 6) e escrita de `.xlsx` (Etapa 11) |
| Gráficos | Chart.js 4.4.4 (CDN) | Primeira lib de gráfico do projeto, sem dependência Python |
| Frontend estático | Bootstrap 5.3.2 + Font Awesome 6.4.0 (CDN) | Sem `django-leaflet`, `geopandas` ou `pandas` no projeto |
| Servidor web de produção | Nginx | **Citado nos requisitos, ainda não implementado** — o projeto roda `python manage.py runserver` diretamente |

Não há `tests.py` em nenhum app do repositório, nem `serializers.py`
DRF.

### 2.2 Diagrama de componentes (texto)

O projeto é dividido em **10 apps Django**, um por domínio, todos
registrados em `INSTALLED_APPS`:

```
geoclima/ (projeto)
│
├── core/        → Home pública + página de Ajuda (/, /ajuda/)
├── accounts/    → autenticação, perfis de usuário, gestão de usuários
├── maps/        → malha municipal do IBGE (Municipio)
├── api/         → endpoints JSON do seletor de município (/api/)
├── farms/       → fazendas, talhões, shapefile, exportação, relatório
├── stations/    → estações de medição de chuva
├── climate/     → lançamento/importação de chuva, CHIRPS, validação,
│                  correção, tendência/cenários (Projection)
├── spi/         → cálculo do SPI, alertas climáticos derivados do SPI
├── alerts/      → model Alert (consumido por climate/ e spi/)
└── dashboard/   → painel privado (agregações, gráficos, insights)
```

Relações entre apps (dependências de import, não hierarquia de
diretórios):

- `farms` depende de `maps` (FK `Farm.municipio`) e de `climate`/`spi`
  (leitura de dados agregados para exibição/exportação).
- `stations` depende de `farms` (FK `Station.farm`).
- `climate` depende de `maps` (FK `ChirpsData.municipio`) e de
  `stations`/`farms` (dado local).
- `spi` depende de `climate` (fonte do CHIRPS) e de `maps`
  (iteração por município `ativo=True`); `spi.alert_checks` depende de
  `alerts`.
- `dashboard` depende de `farms`, `climate`, `spi` e `alerts`
  (agregações para exibição — não persiste nada, `dashboard/models.py`
  está vazio).
- `accounts` depende só de `django.contrib.auth`.
- `core` depende de `dashboard`/`accounts` apenas para montar links de
  navegação.

Todas as rotas privadas ficam sob o prefixo `/painel/`:
`/painel/` (dashboard), `/painel/fazendas/` (farms),
`/painel/estacoes/` (stations), `/painel/chuva/` (climate),
`/painel/usuarios/` (accounts, gestão de usuários — namespace
`gestao_usuarios`). As rotas de autenticação ficam em `/accounts/`
(login, registro, recuperação de senha). A rota pública `/ajuda/`
(app `core`) não exige login.

### 2.3 Fluxo de dados: CHIRPS → GEE → PostGIS → SPI → Dashboard

```
1. Google Earth Engine (coleção pública UCSB-CHG/CHIRPS/DAILY)
        │
        │  reduceRegion(Reducer.mean()) sobre o polígono do município
        │  (climate/management/commands/import_chirps.py)
        ▼
2. climate.ChirpsData (PostgreSQL/PostGIS)
   — 1 registro por (município, dia): média zonal de chuva
   — atualizado diariamente às 04:00 America/Cuiaba (climate/tasks.py,
     Celery Beat)
        │
        │  agregação mensal + rolling sum (spi/services.py)
        ▼
3. spi.SpiResult (PostgreSQL)
   — SPI-3/6/12 por estação, calculado via
     management command calcular_spi
        │
        │  leitura on-the-fly (dashboard/services.py:serie_spi)
        │  + interpretação por regras (dashboard/insights.py)
        ▼
4. Dashboard privado (/painel/)
   — gráfico de tendência do SPI (Chart.js)
   — cartão de Insights (texto interpretativo)
   — alertas climáticos (spi/alert_checks.py → alerts.Alert)
```

Em paralelo, o dado **local** (lançado manualmente ou importado via
CSV/Excel, `climate.RainfallData`) é comparado ao CHIRPS
(`climate/validation.py`) para gerar `climate.ChirpsValidation`, cujo
resultado (MBE) é usado por `climate/correction.py` para corrigir o
CHIRPS bruto exibido ao usuário — sem alterar o dado gravado nem
realimentar o cálculo do SPI.

---

## 3. Base de dados

### 3.1 Uso do PostGIS e por quê

O projeto usa `django.contrib.gis` com backend
`django.contrib.gis.db.backends.postgis` desde a Etapa 1. A decisão é
estrutural: o sistema lida nativamente com geometrias (pontos de
fazenda/estação, polígonos de município/propriedade) e precisa de
operações espaciais (reprojeção de coordenadas, simplificação de
geometria, cálculo de centroide, `reduceRegion` espacial no GEE
correspondente ao polígono armazenado). Um banco relacional sem
suporte geoespacial nativo exigiria implementar essas operações fora
do banco ou converter coordenadas manualmente a cada consulta. Todos
os models geoespaciais seguem o mesmo padrão: um campo
`geom = models.PointField(srid=4326, ...)` (ou `MultiPolygonField`)
convivendo com floats `latitude`/`longitude` explícitos — os dois não
se substituem, por decisão documentada em `CLAUDE.md`.

### 3.2 Models principais

| Model (app) | Campos relevantes | Observações |
|---|---|---|
| `User`/`Profile` (`accounts`) | `profile_type` (admin, pesquisador, produtor, tecnico, visitante), `phone`, `created_at` | `OneToOneField(User)`; criado automaticamente via signal `post_save`, sempre com `profile_type="produtor"` no cadastro público |
| `Municipio` (`maps`) | `nome`, `uf`, `codigo_ibge` (único), `geom` (`MultiPolygonField`, SRID 4326), `ativo`, `destaque` | Guarda os 5.573 municípios do Brasil; `ativo` controla processamento científico pesado, `destaque` controla sugestão na Home |
| `Farm` (`farms`) | `name`, `city` (legado, sem uso no form), `municipio` (FK `Municipio`, `on_delete=PROTECT`), `latitude`/`longitude`, `area`, `crop`, `notes`, `geom` (`PointField`), `poligono` (`MultiPolygonField`, opcional), `owner` (FK `User`, `CASCADE`) | `poligono` preenchido via importação de shapefile (Etapa 5) |
| `Talhao` (`farms`) | `name`, `area`, `crop`, `latitude`/`longitude`, `geom`, `farm`/`owner` (FKs `CASCADE`) | Model novo da Etapa 5, sem polígono de contorno |
| `Station` (`stations`) | `name`, `station_type` (davis, ecowitt, ambient, iot, manual, csv), `latitude`/`longitude`, `geom`, `farm`/`owner` (FKs) | |
| `RainfallData` (`climate`) | `date`, `time` (opcional), `value`, `notes` (opcional), `source_type` (chirps, manual, station, imported_csv, api), `station`/`farm`/`owner` (FKs), `unique_together=('date','station','source_type')` | `time`/`notes` adicionados na Etapa 6 |
| `ChirpsData` (`climate`) | `date`, `value`, `latitude`/`longitude`, `geom` (centroide do município), `municipio` (FK, nullable), `station`/`farm`/`owner` (FKs opcionais, sem uso), `unique_together=('municipio','date')` | 33.234 registros (backfill 1981–2026) |
| `ChirpsValidation` (`climate`) | `station` (`OneToOneField`), `farm`/`owner`, `n_pares`, `r2`, `rmse`, `mae`, `mbe`, `indice_d`, `indice_c`, `desempenho_c`, `calculado_em` | 1 resultado por estação — sempre o mais recente, não série temporal |
| `Projection` (`climate`) | `date`, `scenario`, `value`, `station`/`farm`/`owner` (FKs), `unique_together=('date','scenario','station')` (adicionado na Etapa 10.2) | Model do PDF, sem uso de 2026-07-16 até a Etapa 10 |
| `SpiResult` (`spi`) | `date`, `scale` (3/6/12), `value`, `classification` (7 categorias — ver seção 6), `station`/`farm`/`owner` (FKs), `unique_together=('date','scale','station')` | |
| `Alert` (`alerts`) | `alert_type` (drought, excess_rain, water_risk, anomaly, inconsistency), `message`, `created_at`, `is_active`, `station`/`farm`/`owner` (FKs) | 5 tipos, todos com lógica de geração desde a Etapa 9.1 |

**Padrão de isolamento multiusuário**, aplicado em toda tabela de
dado: FKs `owner` (User), `farm` (Farm) e, quando aplicável, `station`
(Station), todas com `on_delete=models.CASCADE` — exceto
`Farm.municipio`, que usa `on_delete=models.PROTECT` (dado de
referência do IBGE, não deve ser apagável enquanto houver fazenda
vinculada).

### 3.3 Os 5.573 municípios do IBGE — importação

O management command `maps/management/commands/import_municipios.py`
(primeiro command do projeto) lê a malha municipal do IBGE 2025
(`data/ibge/BR_Municipios_2025.zip`, ~237 MB, não versionado no
repositório — listado em `.gitignore`) diretamente de dentro do
arquivo `.zip` via GDAL, executa:

1. reprojeção de SIRGAS2000 (SRID 4674, datum original do IBGE) para
   WGS84 (SRID 4326);
2. simplificação de geometria (~13x menor, tolerância configurável via
   `--simplify`);
3. promoção de `Polygon` para `MultiPolygon`;
4. upsert por `codigo_ibge`.

Suporta `--uf` para importar apenas um estado. A execução completa
para o Brasil inteiro levou **~1 minuto**, resultando em **5.573
municípios importados**. Ao final, o próprio comando marca Tangará da
Serra (`codigo_ibge=5107958`) e Cáceres (`codigo_ibge=5102504`) como
`ativo=True, destaque=True` — por código IBGE, nunca por nome/string
em lógica de negócio (ver seção 10, "Plataforma nacional/genérica").

---

## 4. Módulos implementados (etapa por etapa)

O roadmap original do PDF define **10 etapas**; três etapas adicionais
(11, 12, 13) foram implementadas por pedido do usuário após o
fechamento do roadmap original, fora do escopo de `docs/REQUISITOS.md`.

### Etapa 1 — Estrutura base (Docker, Django, PostgreSQL, PostGIS)

- **Implementado:** `Dockerfile` com dependências GDAL/PostGIS;
  `docker-compose.yml` com serviços `db`, `redis`, `web`,
  `celery_worker` (depois `celery_beat`); Django configurado com
  `django.contrib.gis`; 10 apps criados e registrados.
- **Tecnologias:** Django, PostGIS, Docker Compose.
- **Resultado funcional:** ambiente reproduzível via `docker compose up
  --build`.
- **Pendência:** serviço `nginx` citado nos requisitos, ainda não
  presente.

### Etapa 2 — Sistema geoespacial (mapas, municípios, Leaflet)

- **2.1 Home pública** com mapa Leaflet + OpenStreetMap, responsiva,
  geolocalização do usuário com marcador.
- **2.2 Municípios e seletor de localidade** (2026-07-16) —
  `maps.Municipio` com os 5.573 municípios (seção 3.3); seletor
  Estado→Cidade encadeado na Home; endpoints `GET /api/estados/`,
  `GET /api/municipios/?uf=UF`, `GET /api/municipios/<id>/geojson/`.
  Ao escolher a cidade, desenha o polígono no Leaflet e recarrega o
  clima no centroide.
- **Decisão técnica:** estrutura nacional/genérica por design — ver
  seção 10.
- **Pendente:** 2.3 (alternância de camadas climáticas no mapa) não
  implementada; 2.4 parcial (radar/satélite via iframe Windy
  funcional; os 4 cards "Satélite/Queimadas/Chuva Acumulada/Temperatura",
  que eram links `#` sem função real, foram removidos da Home em
  2026-08-23).

### Etapa 3 — Integração CHIRPS ✅ completa (2026-07-16)

- **3.1 Integração via Google Earth Engine:** conta de serviço
  autenticada; `climate.ChirpsData` ganhou FK `municipio`; command
  `import_chirps`. Detalhado na seção 5.
- **3.2 Backfill histórico completo:** 1981-01-01 a 2026-06-30, 92
  blocos, 0 erros, 33.234 registros, 0 buracos, 0 valores negativos.
- **3.3 Task Celery de atualização diária automática:** serviço
  `celery_beat` dedicado, agendamento às 04:00 `America/Cuiaba`.
- **Resultado funcional:** série de precipitação diária, por
  município, mantida em dia automaticamente, sem intervenção manual.

### Etapa 4 — Login e usuários ✅ completa (2026-07-16)

- **Implementado:** autenticação nativa do Django (login, logout,
  registro, recuperação de senha por e-mail); `Profile` criado
  automaticamente via signal, papel padrão `produtor`; admin com
  `Profile` embutido no `User`; `/painel/` protegido por login.
- **Decisão técnica:** sem libs de terceiros (`django-allauth` e
  afins) — ver seção 10.
- **Comando de apoio:** `seed_demo` — cria `admin_demo` e
  `joao.produtor`, idempotente, recusa rodar com `DEBUG=False`.
- **Pendência consciente:** verificação de e-mail por link não
  implementada — aceitável em desenvolvimento/beta fechado, precisa
  ser resolvida antes de beta público.

### Etapa 5 — Fazendas e estações ✅ completa (2026-08-23)

- **Implementado:** CRUD completo de fazenda (`Farm`), talhão (model
  novo `Talhao`) e estação (`Station`); `Farm.city` (texto livre)
  trocado por FK `municipio`; formulários com mapa Leaflet "clique
  para marcar" (sem digitação de coordenadas); importação de
  Shapefile no cadastro de fazenda (polígono vira `Farm.poligono`,
  pontos viram `Station` automaticamente).
- **Isolamento multiusuário testado** no navegador com dois usuários
  diferentes: acesso direto por URL à fazenda de outro usuário retorna
  404.
- **Deliberadamente não expandido:** campo `crop` continua um único
  texto por fazenda/talhão (não virou model de calendário de
  sucessão de safra).

### Etapa 6 — Importação CSV e dados manuais ✅ completa (2026-08-23)

- **Implementado:** `RainfallData` ganhou `time`/`notes`; formulário
  de lançamento manual; importador único de CSV **e** Excel
  (`climate/data_import.py`, nova dependência `openpyxl`), detecção de
  colunas pelo cabeçalho, sem template rígido; gravação idempotente
  (`update_or_create` por estação+data+origem).
- **Resultado funcional:** histórico de lançamentos com editar/excluir.

### Etapa 7 — Cálculo SPI ✅ completa (7.1–7.4)

- **7.1 Lógica de cálculo do SPI** — `spi/services.py`, fórmula
  `SPI=(Xi-X̄)/σ`; command `calcular_spi`. Detalhado na seção 6.
- **7.2 Validação estatística CHIRPS × local** — model novo
  `ChirpsValidation`; `climate/validation.py` calcula R², RMSE, MAE,
  MBE, índice d (Willmott), índice c (Camargo-Sentelhas); command
  `validar_chirps`.
- **7.3 Detecção de inconsistências** — `climate/quality_checks.py` (4
  checagens: chuva negativa, valor extremo >200mm, valor repetido 3+
  dias, gap de 5+ dias); grava em `alerts.Alert` (tipo novo
  `inconsistency`); command `detectar_inconsistencias`.
- **7.4 Correção/calibração local do CHIRPS** — `climate/correction.py`,
  correção aditiva de viés (`valor_corrigido = valor_chirps − mbe`),
  calculada on-the-fly, sem model nem command novos.
- **Restrição de dado (não de código) em toda a Etapa 7:** só funciona
  hoje para municípios `ativo=True` (Tangará da Serra/Cáceres), porque
  só esses têm CHIRPS importado.

### Etapa 8 — Dashboards e gráficos ✅ completa (8.1–8.3)

- **8.1 Estrutura do dashboard** — `dashboard/services.py`
  (`chuva_atual`, `acumulados`, `serie_chuva`, on-the-fly, sem model
  novo); view `painel` estendida com seletor de fazenda; gráfico de
  linha "Série de Chuva" com Chart.js (primeira lib de gráfico do
  projeto).
- **8.2 Tendência do SPI + comparação CHIRPS×local em gráfico** —
  `serie_spi(farm)` (uma linha por data, colunas SPI-3/6/12);
  `comparacao_chirps_local(farm)` (gráfico de dispersão com linha de
  referência y=x).
- **8.3 Mapa geral + previsão climática** — mapa Leaflet com todas as
  fazendas do usuário; previsão climática via Open-Meteo, buscada
  client-side.

### Etapa 9 — Alertas e insights automáticos ✅ completa (9.1–9.2)

- **9.1 Alertas automáticos** — `spi/alert_checks.py`, 4 tipos (seca,
  excesso de chuva, risco hídrico, anomalia), cada um numa combinação
  diferente de escala/severidade do SPI; command
  `detectar_alertas_climaticos`.
- **9.2 Insights para tomada de decisão** — `dashboard/insights.py`,
  texto interpretativo baseado em regras, sem IA/ML.
- Detalhado na seção 7.
- **Pendência consciente:** notificações (email/WhatsApp) não
  implementadas — o PDF já marca esse item como "futuro".

### Etapa 10 — Projeções climáticas ✅ completa

- **10.1 Análise histórica + tendência temporal** — `climate/trends.py`,
  regressão linear simples sobre totais anuais (`statistics.linear_regression`).
- **10.2 Cenários futuros (climatologia histórica)** — 3 faixas
  (seco/normal/úmido = percentis 25/50/75) para os próximos meses,
  persistidas em `climate.Projection` via command `gerar_projecoes`.
- **Decisão confirmada com o usuário antes de codar:** sem machine
  learning/IA/modelos preditivos — explicitamente "Futuro" no PDF.
- Esta era a última etapa do roadmap original de 10 etapas.

### Etapa 11 — Exportação de dados (fora do escopo original do PDF) ✅ completa

- **Exportação Excel:** `farms/exports.py`, `.xlsx` com 9 abas
  (Fazenda, Estações, Talhões, Chuva Local, CHIRPS do Município, SPI,
  Validação CHIRPS, Alertas, Cenários Futuros).
- **Relatório para imprimir/PDF:** página standalone
  `farms/relatorio_fazenda.html`, CSS `@media print`, "PDF" via
  recurso nativo do navegador (`window.print()`) — sem biblioteca de
  geração de PDF no servidor.

### Etapa 12 — Manual de uso do sistema (fora do escopo original do PDF) ✅ completa

- Página de Ajuda pública (`GET /ajuda/`), 8 seções em ordem
  cronológica de uso, com índice de âncoras.

### Etapa 13 — Gestão de usuários (completa parte do que a Etapa 4 do PDF deixou em aberto) ✅ completa

- `accounts/views_gestao.py`: bloquear/desbloquear usuário
  (`User.is_active`) e trocar perfil (`Profile.profile_type`), restrito
  a administradores, rota `/painel/usuarios/`.

---

## 5. Processamento de dados climáticos

### 5.1 CHIRPS — o que é e como é acessado

**CHIRPS** (Climate Hazards Group InfraRed Precipitation with Station
data) é um produto de estimativa de precipitação por sensoriamento
remoto, mantido pelo Climate Hazards Center (UC Santa Barbara), com
série histórica diária desde 1981. O projeto usa a coleção pública do
Google Earth Engine `UCSB-CHG/CHIRPS/DAILY`, **não** download direto
dos arquivos `.tif`/`.bil` do servidor da UCSB — decisão registrada em
`docs/DECISOES.md` (ver seção 10): o GEE já mantém o CHIRPS pronto
para consulta espacial sem exigir processamento local de raster bruto.

**Resolução/escala de extração:** a redução espacial usa `scale =
5.566 m` (~0,05°, resolução nativa do CHIRPS). A estratégia adotada é
**média zonal por município**, não célula-grade individual: para cada
dia, o CHIRPS é reduzido (`ee.Reducer.mean()` via `reduceRegion`)
sobre o polígono inteiro do município (já simplificado por
`import_municipios`), gerando **um valor por município por dia**.

### 5.2 Conta de serviço Google — como funciona

Autenticação server-side via **conta de serviço** do Google Cloud
(`geoclima-gee-import@climatga.iam.gserviceaccount.com`), projeto GCP
`climatga` (nome de exibição "climaTga" — o ID real do projeto, usado
em toda configuração, é sempre minúsculo). Chave JSON em
`secrets/gee-key.json`, não versionada (`secrets/` no `.gitignore`),
montada nos containers via bind mount já existente (`.:/app`).
`GEE_PROJECT_ID` e `GEE_SERVICE_ACCOUNT_KEY_PATH` são lidas de
variáveis de ambiente (`docker-compose.yml` → `geoclima/settings.py`).

**Papéis IAM necessários** (identificados por troubleshooting real
durante o desenvolvimento, registrados em `docs/HISTORICO.md`):

1. **Earth Engine Resource Viewer** — permite ler metadados, mas não
   executar computação.
2. **Earth Engine Resource Writer** — necessário mesmo para leitura
   agregada via `reduceRegion` (a permissão
   `earthengine.computations.create` é exigida para qualquer
   computação, inclusive as de leitura).
3. **Service Usage Consumer** (`roles/serviceusage.serviceUsageConsumer`)
   — sem esse papel, ocorre erro `403 USER_PROJECT_DENIED`.

Um detalhe operacional relevante para reprodução futura: ao conceder
múltiplos papéis pela tela do IAM do Google Cloud, é necessário usar
"+ Adicionar outro papel" — editar o papel existente **substitui** em
vez de somar, o que fez um dos erros reaparecer durante a configuração
inicial.

### 5.3 Import idempotente — lógica e por quê

O management command `climate/management/commands/import_chirps.py`
(`--start`/`--end`/`--municipio`/`--chunk-days`) grava cada registro
via `update_or_create` usando `(municipio, date)` como chave. Rodar o
mesmo período novamente **atualiza** em vez de duplicar — comportamento
necessário porque a task diária (seção 5.5) pode ser executada mais de
uma vez sobre o mesmo intervalo sem risco de inconsistência, e porque
permite reprocessar um período específico (ex.: correção de uma falha)
sem produzir registros duplicados. Períodos longos são processados em
blocos (`--chunk-days`, padrão 365 dias) — dentro de cada bloco, a
série diária inteira é reduzida no servidor via `ImageCollection.map()`
numa única chamada de rede (`.getInfo()`), não uma requisição por dia.

### 5.4 Backfill 1981 → hoje — volume de dados e estratégia

O backfill histórico completo (Etapa 3.2, executado em 2026-07-16)
cobriu o período de **1981-01-01 a 2026-06-30** (última data
efetivamente publicada no CHIRPS no momento da execução — consultada
via GEE, não assumida como "hoje", para não gravar zero em dia ainda
não publicado). Estratégia: blocos de 365 dias, processados em
sequência.

**Resultado:** 92 blocos processados (46 anos × 2 municípios ativos),
**0 erros**, **0 blocos com retry**. Total de **33.234 registros**
(16.617 por município), **0 buracos** na série, **0 valores
negativos**. Resumo por década (média de precipitação anual):

| Município | Décadas completas (1980–2010) | 6 anos de 2020 |
|---|---|---|
| Tangará da Serra/MT | ~1.694–1.873 mm/ano | 1.578,3 mm/ano |
| Cáceres/MT | ~1.176–1.272 mm/ano | 996,6 mm/ano |

Tangará da Serra é consistentemente mais chuvosa que Cáceres em todas
as décadas — coerente com a posição geográfica das duas cidades
(transição amazônica vs. transição pantaneira). A década de 2020
aparece mais seca nas duas cidades nesse recorte, mas com amostra de
apenas 6 anos — o próprio `docs/HISTORICO.md` registra que nenhuma
conclusão foi tirada sobre isso no desenvolvimento, deixando essa
interpretação para a dissertação.

### 5.5 Task Celery diária — o que faz, frequência

`climate/tasks.py` define a task `atualizar_chirps` (`@shared_task`),
agendada em `geoclima/celery.py` (`app.conf.beat_schedule`) via
`crontab(hour=4, minute=0)` — **todo dia às 04:00, horário
`America/Cuiaba`** — executada pelo serviço Docker dedicado
`celery_beat` (separado do `celery_worker`; justificativa na seção
10). A task **não duplica** a lógica de extração: para cada município
`ativo=True`, calcula o intervalo entre a última data já gravada em
`ChirpsData` e a última data publicada no GEE, e chama o próprio
`import_chirps` via `django.core.management.call_command`. Se não
houver nada novo (defasagem normal de publicação do CHIRPS, de
~2-3 semanas), a ausência de dado novo é logada como `INFO`, não como
erro. Retry declarativo: `autoretry_for=(Exception,)` +
`retry_backoff=True` (backoff exponencial até 10 min) + `max_retries=5`;
falha em um município não aborta os demais na mesma execução.

---

## 6. Cálculo do SPI

### 6.1 Definição

O **SPI** (Standardized Precipitation Index), formulado por McKee,
Doesken e Kleist (1993), é um índice estatístico que padroniza a
precipitação acumulada de uma janela de tempo em relação à
distribuição histórica da mesma janela, no mesmo período do
calendário. O projeto segue **literalmente a fórmula dada em
`docs/REQUISITOS.md`**:

```
SPI = (Xi - X̄) / σ
```

um z-score simples — **não** o método McKee "oficial" completo (que
ajusta uma distribuição Gama à série antes de padronizar, exigindo a
biblioteca `scipy`). A escolha de seguir a fórmula literal do PDF, em
vez de substituir por um método estatisticamente mais sofisticado que
não foi pedido, está registrada explicitamente em `docs/DECISOES.md`.

### 6.2 Escalas implementadas

`docs/REQUISITOS.md` pede: **SPI-3, SPI-6, SPI-12** (o documento de
requisitos não solicita SPI-1; nenhuma escala além dessas três foi
implementada — `spi/services.py:ESCALAS_VALIDAS = (3, 6, 12)`).

### 6.3 Classificação — 7 faixas

O PDF define apenas os **nomes** das categorias de classificação, sem
os limiares numéricos. O projeto adotou os limiares padrão da
literatura (McKee et al., 1993). A tabela de classificação
(`spi/services.py:LIMIARES_CLASSIFICACAO`), atualizada em
2026-08-23 para incluir a faixa "moderadamente úmido" (originalmente
ausente, corrigida numa revisão posterior — ver seção 10, entradas
finais):

| Faixa de SPI | Classificação | Rótulo (`SpiResult.CLASSIFICATIONS`) |
|---|---|---|
| ≥ 2,0 | Extremamente úmido | `extremamente_umido` |
| 1,5 a 1,99 | Muito úmido | `muito_umido` |
| 1,0 a 1,49 | Moderadamente úmido | `moderadamente_umido` |
| -0,99 a 0,99 | Normal | `normal` |
| -1,0 a -1,49 | Seca moderada | `seca_moderada` |
| -1,5 a -1,99 | Seca severa | `seca_severa` |
| ≤ -2,0 | Seca extrema | `seca_extrema` |

A migration `spi/migrations/0002_alter_spiresult_classification.py`
adicionou `moderadamente_umido` ao `choices` do model `SpiResult` —
antes dessa correção, o `classificar_spi()` já podia retornar esse
valor, mas o model só reconhecia 6 categorias.

### 6.4 Como é calculado no sistema

`spi/services.py:calcular_serie_spi(municipio, escala)`:

1. Agrega `climate.ChirpsData` (diário) em totais **mensais** por
   município.
2. Para a escala pedida (3, 6 ou 12 meses), monta a soma corrente
   (rolling) dos últimos N meses, terminando em cada mês da série.
3. Agrupa esses valores por **mês do calendário** — ex.: todos os
   "SPI-3 terminando em março", de todos os anos disponíveis — formando
   a distribuição climatológica de referência daquele mês/escala.
   Exige um mínimo de **10 anos de histórico** no mesmo mês
   (`MINIMO_ANOS_HISTORICO = 10`, limiar conservador do projeto, não
   uma norma oficial).
4. Padroniza (z-score) cada valor contra a média/desvio-padrão do seu
   próprio grupo de mês.
5. Classifica o resultado nas 7 categorias da seção 6.3.

O management command `spi/management/commands/calcular_spi.py`
(`--scale`/`--municipio`) itera `maps.Municipio.objects.filter(ativo=True)`
e grava um `SpiResult` por estação de cada fazenda do município, via
`update_or_create` (idempotente). Como o SPI é regional (por
município) mas o model exige FK `station`, o mesmo valor é gravado
redundantemente para cada estação do município — decisão documentada
em `docs/DECISOES.md` para evitar uma migration adicional de schema
sem necessidade comprovada.

**Restrição de dado, não de código:** o SPI só é calculável hoje para
municípios `ativo=True` (Tangará da Serra e Cáceres), porque só esses
têm histórico de CHIRPS importado — nenhum nome ou código de
município aparece em condicional de código em `spi/`.

---

## 7. Sistema de alertas e insights

### 7.1 Tipos de alerta

`alerts.Alert.alert_type` define **5 tipos**, todos com lógica de
geração ativa desde a Etapa 9.1:

| Tipo | Origem | Fonte de dado | Critério |
|---|---|---|---|
| `inconsistency` (Possível Inconsistência) | Etapa 7.3 | `climate.RainfallData` (dado local) | 4 checagens: chuva negativa, valor extremo (>200mm), valor repetido 3+ dias seguidos, gap de 5+ dias sem lançamento |
| `drought` (Alerta de Seca) | Etapa 9.1 | `spi.SpiResult`, SPI-3 mais recente | classificação em seca_moderada/severa/extrema |
| `excess_rain` (Excesso de Chuva) | Etapa 9.1 | SPI-3 mais recente | classificação em muito_umido/extremamente_umido |
| `water_risk` (Risco Hídrico) | Etapa 9.1 | SPI-6 mais recente | classificação em seca_severa/extrema |
| `anomaly` (Anomalia Climática) | Etapa 9.1 | SPI-12 mais recente | classificação em seca_extrema/extremamente_umido |

A diferenciação de escala/severidade entre os 4 tipos climáticos
(`drought`/`excess_rain`/`water_risk`/`anomaly`) é uma decisão de
interpretação do projeto, já que o PDF não especifica o critério
técnico de cada alerta — apenas os nomes (ver seção 10).

Os alertas `inconsistency` (sobre a **qualidade do dado** lançado pelo
usuário) e os 4 alertas climáticos (sobre o **clima em si**) são
gravados no mesmo model `Alert`, mas exibidos em cartões separados na
interface, para não confundir as duas naturezas de alerta.

### 7.2 Lógica dos insights — descritivo, não prescritivo

`dashboard/insights.py:gerar_insights(dados_spi, alertas_climaticos)`
interpreta, por **regras** (sem IA/ML), o SPI mais recente e os
alertas climáticos já gerados, cobrindo os 7 tipos de insight pedidos
em `docs/REQUISITOS.md` ("Insights para Tomada de Decisão": risco de
déficit hídrico, tendência de seca, janela favorável de plantio, risco
climático, necessidade de irrigação, tendência pluviométrica, apoio à
gestão hídrica), agrupados em **4 sinais distintos** (vários itens do
PDF são a mesma leitura climática reformulada — déficit
hídrico/irrigação/janela de plantio, por exemplo, derivam todos do
mesmo SPI-3 atual).

**Revisão explícita de linguagem** (2026-08-23, posterior à
implementação original): a primeira versão do módulo continha frases
prescritivas ("pode ser hora de considerar irrigação", "não é janela
favorável pra plantio de sequeiro"), que confundiam a leitura
estatística do SPI com uma recomendação agronômica — recomendação que
o sistema não tem base para fazer, pois não considera cultura, estágio
fenológico, tipo de solo ou capacidade de armazenamento hídrico do
produtor. O sistema foi reescrito para **descrever** o estado da
anomalia de precipitação, não recomendar ação. Também foi corrigida a
confusão conceitual entre "umidade do solo" e "anomalia de
precipitação" (o que o SPI de fato mede) — toda menção a "solo" foi
substituída por linguagem de precipitação acumulada.

### 7.3 Contexto sazonal de MT na tendência

`dashboard/insights.py:_insight_tendencia` compara a variação do SPI-3
nos últimos 3 meses disponíveis. A versão original comparava o valor
bruto sem considerar que Mato Grosso tem uma **transição
chuvoso→seco previsível todo ano** (abril–setembro) — uma queda de
SPI nesse período é o comportamento esperado da estação, não um sinal
de alerta. Correção aplicada:

- se a janela de 3 meses cai **inteiramente dentro de abril–setembro**,
  a queda é contextualizada como sazonal esperada ("consistente com a
  transição sazonal — comportamento esperado pra a época");
- fora desse intervalo (outubro–março, estação chuvosa em MT), uma
  queda **≥ 0,5** no SPI-3 é sinalizada como tendência atípica que
  merece acompanhamento;
- melhora e estabilidade não mudaram de comportamento com o mês.

Essa correção foi validada com dado real da fazenda "fazenda Rocha":
antes da correção, um SPI-3 caindo de 1,41 (maio) para -0,16 (julho)
gerava um alerta de "tendência de piora" — um falso positivo, já que
maio–julho é justamente a transição sazonal normal da região. Após a
correção, a mesma série gera a leitura contextualizada correta.

### 7.4 Decisões documentadas relevantes

- **Sem IA/ML:** decisão confirmada explicitamente com o usuário antes
  de codar a Etapa 9.2 — o próprio `docs/REQUISITOS.md` marca "machine
  learning; IA climática; modelos preditivos" como **"Futuro"**, fora
  do escopo funcional das etapas centrais do sistema.
- **Sem notificações (email/WhatsApp):** mesmo tratamento — marcado
  como "futuro" no PDF, confirmado como fora de escopo por decisão
  explícita do usuário.
- **Threshold de tendência (`LIMIAR_TENDENCIA = 0.3`):** limiar
  empírico do projeto, sem referência bibliográfica publicada —
  documentado explicitamente como tal no código, para não sugerir uma
  origem científica que não existe. Um segundo limiar
  (`LIMIAR_QUEDA_ATIPICA = 0.5`), separado do primeiro, decide o que
  conta como queda atípica fora do período seco.
- **Reaproveitamento de código:** `dashboard/insights.py` reaproveita
  `spi.services.classificar_spi` (não duplica os limiares de
  classificação) e os alertas já gerados por `spi/alert_checks.py`
  (não recalcula nada).

---

## 8. Frontend e visualização

### 8.1 Home com Open-Meteo

`core/templates/core/index.html` é a página pública única do sistema,
consumindo a API pública da **Open-Meteo** (Forecast API + Air Quality
API) **diretamente do JavaScript do navegador**, sem passar pelo
backend Django — padrão mantido em toda funcionalidade de clima em
tempo real do projeto (inclusive na previsão climática do dashboard
privado, Etapa 8.3). A Home contém: card de clima atual, grade de
micro-detalhes (vento, rajada, umidade, chuva, visibilidade, pressão,
índice UV, nascer/pôr do sol, AQI), previsão por hora (8h) e por 7
dias, mapa Leaflet com geolocalização do usuário, e um iframe do
Windy.com para radar/satélite em tempo real. Um bloco de 4 cards
"Mapas Agrícolas do Brasil" (Satélite, Queimadas, Chuva
Acumulada/CHIRPS, Temperatura), que eram links `#` sem função real,
foi removido da Home em 2026-08-23, a pedido do usuário.

### 8.2 Mapa com Leaflet

Leaflet + tiles OpenStreetMap é o padrão de mapa usado em **todo** o
sistema — Home, cadastro de fazenda/talhão/estação, detalhe de
fazenda, dashboard privado. O padrão de UI "clique para marcar"
(Etapa 5) é reaproveitado em três formulários: clicar ou arrastar um
marcador preenche `latitude`/`longitude` via JavaScript, sem digitação
manual de coordenadas.

### 8.3 Seletor estado/cidade

Implementado na Etapa 2.2 (`api/views.py`, endpoints `JsonResponse`
simples, sem DRF), reaproveitado em toda tela que precisa de um
município (Home, cadastro de fazenda). Dois `<select>` encadeados
(Estado → Cidade), com optgroup de destaques (Tangará da
Serra/Cáceres). Ao trocar a cidade, o polígono do município é
desenhado no Leaflet (`fitBounds`) via `GET
/api/municipios/<id>/geojson/`.

### 8.4 Dashboard privado por fazenda

`/painel/` (app `dashboard`), estendido em três sub-etapas (8.1–8.3) a
partir do placeholder pós-login da Etapa 4. Para a fazenda selecionada
no seletor (`?fazenda=<id>`):

- **Insights** (texto interpretativo, seção 7.2);
- **Mapa das Minhas Fazendas** (todas as fazendas do usuário, não só a
  selecionada);
- **Previsão Climática** (Open-Meteo, client-side);
- **Chuva Atual** e **Acumulados** (7/30/90 dias, dado local × CHIRPS
  separados — nunca somados no mesmo número);
- **Série de Chuva** (gráfico de linha);
- **Tendência do SPI** (gráfico de linha, 3 séries);
- **Comparação CHIRPS × Dado Local** (gráfico de dispersão).

### 8.5 Gráficos de SPI

Implementados com **Chart.js 4.4.4 via CDN** (primeira biblioteca de
gráfico do projeto, carregada no mesmo padrão do Leaflet — sem
dependência Python nova). O gráfico de tendência do SPI usa
`dashboard/services.py:serie_spi(farm)`, que devolve **uma linha por
data** com as 3 escalas como colunas (não uma lista por escala) — SPI-12
só começa bem depois de SPI-3 (precisa de 12 meses de janela móvel), e
alinhar por índice de array em vez de por data desalinharia as
séries no gráfico. O parâmetro `spanGaps: true` do Chart.js permite
que a linha de SPI-12 pule os meses ainda sem valor sem quebrar
visualmente.

---

## 9. Infraestrutura

### 9.1 Docker — serviços no compose

`docker-compose.yml` define **5 serviços**:

| Serviço | Imagem/Build | Comando |
|---|---|---|
| `db` | `postgis/postgis:15-3.3-alpine` | — (porta 5432) |
| `redis` | `redis:7-alpine` | — (porta 6379, broker/backend do Celery) |
| `web` | build local (`Dockerfile`) | `python manage.py runserver 0.0.0.0:8000` |
| `celery_worker` | build local | `celery -A geoclima worker --loglevel=info` |
| `celery_beat` | build local | `celery -A geoclima beat --loglevel=info --schedule=/tmp/celerybeat-schedule` |

`celery_beat` é um serviço **separado** de `celery_worker` — decisão
justificada na seção 10. O `--schedule` aponta para `/tmp` dentro do
container (fora do bind mount `.:/app`) para o arquivo de estado do
agendador não aparecer no repositório.

`Dockerfile` parte de `python:3.11-slim` e instala dependências de
sistema necessárias para GDAL/PostGIS: `binutils`, `gdal-bin`,
`libgdal-dev`, `libproj-dev`, `postgresql-client`, `build-essential`.

### 9.2 Variáveis de ambiente

Definidas em `docker-compose.yml` para os serviços `web`,
`celery_worker` e `celery_beat`:

| Variável | Valor (desenvolvimento) | Uso |
|---|---|---|
| `DEBUG` | `True` | Django |
| `DB_NAME` | `geoclima` | Postgres |
| `DB_USER` | `geoclima_user` | Postgres |
| `DB_PASSWORD` | `geoclima_password` | Postgres |
| `DB_HOST` | `db` | Postgres |
| `DB_PORT` | `5432` | Postgres |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker/backend |
| `GEE_PROJECT_ID` | `climatga` | Autenticação Earth Engine |
| `GEE_SERVICE_ACCOUNT_KEY_PATH` | `/app/secrets/gee-key.json` | Autenticação Earth Engine |

A chave de serviço do Google (`secrets/gee-key.json`) não é
versionada — é montada via o bind mount já existente (`.:/app`), e o
diretório `secrets/` está listado em `.gitignore`.

### 9.3 Como subir o ambiente do zero

Sequência reconstruída a partir de `docs/HISTORICO.md` e `README.md`:

```bash
# 1. Construir e subir os containers
docker compose up --build -d

# 2. Aplicar as migrations
docker compose exec web python manage.py migrate

# 3. Importar a malha municipal do IBGE (arquivo em data/ibge/,
#    não versionado — ver docstring do comando para onde obtê-lo)
docker compose exec web python manage.py import_municipios

# 4. Colocar a chave de serviço do Google em secrets/gee-key.json
#    (não versionada) e importar o histórico do CHIRPS
docker compose exec web python manage.py import_chirps \
    --start 1981-01-01 --end <última-data-publicada>

# 5. Calcular SPI, validação e cenários (municípios ativo=True)
docker compose exec web python manage.py calcular_spi
docker compose exec web python manage.py validar_chirps
docker compose exec web python manage.py gerar_projecoes

# 6. Criar usuários de desenvolvimento (opcional, recusa rodar em
#    produção sem --force)
docker compose exec web python manage.py seed_demo
```

A partir daí, a task Celery Beat (`atualizar_chirps`) mantém o CHIRPS
em dia sozinha, sem intervenção manual. Os demais comandos
(`calcular_spi`, `validar_chirps`, `detectar_inconsistencias`,
`detectar_alertas_climaticos`, `gerar_projecoes`) **não** têm
agendamento automático ainda — precisam ser rodados manualmente após
o CHIRPS atualizar.

Credenciais de desenvolvimento (`seed_demo`, documentadas no
`README.md`, marcadas "somente desenvolvimento"):

| Usuário | Senha | Perfil |
|---|---|---|
| `admin_demo` | `AdminDemo#2026` | admin (+ superusuário Django) |
| `joao.produtor` | `Produtor#2026` | produtor |

---

## 10. Decisões técnicas relevantes

Lista cronológica de todas as decisões registradas em
`docs/DECISOES.md`, com justificativa resumida.

1. **Plataforma nacional/genérica, pesquisa focada em MT** (2026-07-16)
   — `maps.Municipio` guarda todos os municípios do Brasil; região
   nunca é condição em código Python, sempre dado no banco (`ativo`/
   `destaque`). Evita que expansão futura exija mexer em código de
   produção.

2. **Fonte do CHIRPS: Google Earth Engine, não download direto**
   (2026-07-16) — o GEE já mantém o CHIRPS pronto para consulta
   espacial. Extração por média zonal municipal, não célula-grade.

3. **Celery Beat como serviço separado do worker** (2026-07-16) —
   rodar o beat embutido no worker só é seguro com exatamente 1
   worker; um serviço dedicado evita disparo duplicado de tarefa se o
   worker for escalado no futuro. Schedule estático em código (não
   `django-celery-beat`), porque só existe uma tarefa periódica hoje.

4. **Autenticação nativa do Django, sem libs de terceiros** (Etapa 4)
   — os requisitos são exatamente o que `django.contrib.auth` já
   resolve; `django-allauth` compensaria só com login social ou
   múltiplos métodos de autenticação, nenhum pedido.

5. **`Farm.municipio` com `on_delete=PROTECT`** (Etapa 5) — diferente
   do padrão `CASCADE` do projeto: `Municipio` é dado de referência do
   IBGE, não deve ser apagável enquanto houver fazenda vinculada.

6. **Importação de Shapefile no cadastro de fazenda** (2026-08-23) —
   convive com o clique manual no mapa; múltiplos polígonos são
   unidos num `MultiPolygon` (fazenda pode ter parcelas
   não-contíguas); pontos viram `Station` automaticamente.

7. **Cultura agrícola como campo único, não expandido** (2026-08-23) —
   modelar sucessão de safra/safrinha é escopo maior, que faz mais
   sentido desenhar junto com a Etapa 9 (insights), quando o "para
   quê" ficar claro.

8. **Lição aprendida: nunca `.delete()` sem filtro por dono**
   (2026-08-23) — um `Farm.objects.all().delete()` sem filtro apagou
   dado real de um usuário durante o desenvolvimento (sem backup
   configurado, perda definitiva). Regra registrada para qualquer
   sessão futura.

9. **Etapa 6 — `openpyxl` como dependência nova** — decisão explícita
   do usuário (CSV+Excel juntos, em vez de só CSV). Parser único
   detecta colunas pelo cabeçalho, sem template rígido.

10. **Etapa 7.1 — fonte do SPI é só CHIRPS** — `RainfallData` do
    usuário ainda não tem histórico longo o bastante. Fórmula seguida
    literalmente do PDF (z-score simples, não McKee "oficial" com
    distribuição Gama). `SpiResult.station` mantido obrigatório
    (redundância aceita) em vez de nova migration de schema.

11. **Etapa 7.2 — `ChirpsValidation` como `OneToOneField`** — retrato
    sempre mais recente, não série temporal (diferente do
    `SpiResult`). Índice c = `r × d` (não `r² × d`), padrão
    agrometeorológico brasileiro (Camargo & Sentelhas, 1997).

12. **Etapa 7.3 — reaproveitar `alerts.Alert`** — o próprio PDF já
    fala em "alertas automáticos" na seção de detecção de
    inconsistências, evitando criar um model paralelo.

13. **Etapa 7.4 — correção aditiva, on-the-fly, sem realimentar o
    SPI** — `valor_corrigido = valor_chirps − mbe`; não persiste
    série corrigida; a correção é por estação, o SPI é por município,
    misturar os dois exigiria uma decisão de agregação não pedida no
    PDF.

14. **Etapa 8.1 — agregação por fazenda, dado local e CHIRPS nunca
    somados** — um usuário pode ter fazendas em municípios diferentes;
    somar medição de campo com estimativa de satélite no mesmo total
    produziria um número que parece mais preciso do que é.

15. **Etapa 8.2 — SPI como uma linha por data (não por escala)** —
    evita desalinhamento de datas no gráfico, causado pelo início
    tardio do SPI-12. Gráfico de dispersão para comparação CHIRPS×local,
    com linha de referência y=x.

16. **Etapa 8.3 — mapa mostra todas as fazendas; previsão é
    client-side** — mesma consistência da Home (sem proxy Django novo
    para a Open-Meteo).

17. **Etapa 9.1 — cada alerta climático usa uma escala diferente do
    SPI** — critério de projeto (não vem do PDF): SPI-3 para impacto
    de curto prazo, SPI-6 para planejamento de médio prazo, SPI-12
    para desvio estrutural de longo prazo — evita duplicar o mesmo
    sinal em alertas diferentes.

18. **Etapa 9.2 — insights agrupam 7 itens do PDF em 4 sinais** —
    evita repetir a mesma leitura climática em frases quase-idênticas;
    reaproveita `classificar_spi` sem duplicar limiares.

19. **Etapa 10 — cenário futuro = climatologia histórica, não
    previsão de verdade** — percentis 25/50/75 do histórico do mesmo
    mês, não modelagem preditiva (explicitamente fora de escopo).
    Tendência é regressão linear simples, calculada on-the-fly;
    cenários são persistidos em `Projection` (model já existia, sem
    uso, desde a Etapa 1).

20. **Etapa 11 — Excel em uma aba múltipla, sem geração de PDF no
    servidor** — evita adicionar `WeasyPrint` (dependências de sistema
    pesadas, risco de quebrar o build Docker); "PDF" é o recurso
    nativo do navegador via impressão.

21. **Etapa 12 — página de Ajuda pública, estendendo `base.html`** —
    ajuda quem ainda não tem conta a decidir se cadastra; a Home não
    usa `base.html` (template já testado, não alterado), por isso o
    link precisou ser adicionado em dois lugares.

22. **Etapa 13 — acesso de administrador checa `is_superuser` OU
    `profile_type='admin'`** — contas podem ter só um dos dois
    setados dependendo de como foram criadas. Proteção explícita
    contra autobloqueio. Rota de gestão de usuários separada das
    rotas públicas de autenticação.

23. **Refatoração dos Insights — correção de linguagem prescritiva e
    contexto sazonal** (2026-08-23) — ver seção 7.2/7.3 para detalhe
    completo; inclui a correção da faixa `moderadamente_umido`
    faltante na classificação do SPI e a migration correspondente em
    `SpiResult.CLASSIFICATIONS`.

---

*Fim do relatório. Compilado integralmente a partir da documentação e
do código-fonte do repositório GeoClima MT em 2026-08-23 — nenhuma
informação foi inferida além do que está registrado nesses arquivos.*
