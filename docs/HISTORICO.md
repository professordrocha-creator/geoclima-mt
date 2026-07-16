# Histórico de Desenvolvimento — GeoClima MT

> Changelog do projeto. As entradas de 2026-06-19 foram migradas de
> `requisitos/requisitos.md` (arquivo original mantido intacto no repo).

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
