# Decisões de Projeto — GeoClima MT

> Registro de decisões arquiteturais que não são óbvias a partir do código
> e que devem ser respeitadas em qualquer trabalho futuro. Ao contrário de
> `docs/ARQUITETURA.md` (o que existe) e `docs/ROADMAP.md` (o que falta),
> este arquivo guarda o **porquê** de escolhas estruturais.

## 2026-07-16 — Plataforma nacional/genérica, pesquisa focada em MT

**Decisão:** o GeoClima MT é o sistema de um mestrado cuja pesquisa valida
dados de precipitação (CHIRPS) para **Tangará da Serra** e **Cáceres**
(MT). Apesar disso, a plataforma em si **nasce genérica para qualquer
município do Brasil**. Região/localidade é sempre **dado no banco**, nunca
uma condição escrita em código Python (`if municipio == "Tangará da
Serra"` está proibido em qualquer camada de backend/API).

**Por quê:** a pesquisa é o caso de uso inicial, não o limite do sistema.
Se o código tivesse nomes de cidade hardcoded em views/serializers/queries,
qualquer expansão futura (outro município, outro estado) exigiria mexer em
código de produção em vez de só popular uma tabela.

**Como isso é aplicado na prática (Etapa 2.2 — municípios):**

- `maps.Municipio` guarda **todos** os municípios do Brasil (malha do
  IBGE), com dois booleanos de controle:
  - `ativo` — processamento de dados científicos pesados (CHIRPS
    histórico, SPI, validação — Etapas 3 e 7) habilitado para esse
    município. Hoje só Tangará da Serra e Cáceres têm `ativo=True`.
  - `destaque` — aparece como sugestão principal no seletor da Home. Hoje
    também só Tangará da Serra e Cáceres.
- O management command `import_municipios` marca esses dois municípios
  como `ativo=True, destaque=True` **pelo `codigo_ibge`** (5107958 e
  5102504), não por comparação de nome/string em lógica de negócio — é uma
  operação de dado (um `UPDATE` equivalente), não uma regra de código.
- Os endpoints da API (`/api/estados/`, `/api/municipios/`,
  `/api/municipios/<id>/geojson/`) não filtram por cidade nenhuma — listam
  o que estiver no banco para a UF pedida, sejam 1 ou 5.570 municípios.

**Exceção deliberada — pré-seleção de UX no frontend:** a Home pré-seleciona
"MT" e "Tangará da Serra" nos dropdowns ao carregar a página, para dar uma
experiência pronta a quem está avaliando o projeto do mestrado. Isso é uma
constante de **interface** (`DEFAULT_MUNICIPIO_IBGE` no JavaScript do
template), não uma condição de backend: ela só define qual `<option>`
começa marcada num `<select>` já populado dinamicamente pela API — qualquer
outro município do Brasil continua selecionável normalmente, e a API por
trás não sabe e não precisa saber que essa constante existe. Se um dia essa
constante for removida do frontend, nada no backend muda.

## Convenção adotada: importação de malha territorial

- Fonte oficial: Portal de Geociências do IBGE → Malhas Territoriais →
  Malhas Municipais → `municipio_2025` → Brasil.
- Arquivos oficiais grandes (shapefiles do IBGE) não vão para o Git — ver
  `.gitignore` (pasta `data/`). O management command que os consome
  (`maps/management/commands/import_municipios.py`) documenta na própria
  docstring onde baixar e onde colocar o arquivo, para que o projeto seja
  reproduzível sem depender do arquivo estar versionado.
- A geometria é simplificada no momento da importação (não em tempo de
  requisição) para manter o banco e o mapa leves — ver detalhes no próprio
  command.

## 2026-07-16 — Fonte do CHIRPS: Google Earth Engine, não download direto

**Decisão:** o CHIRPS é obtido via **Google Earth Engine** (coleção pública
`UCSB-CHG/CHIRPS/DAILY`), não por download direto dos arquivos `.tif`/`.bil`
do servidor da UCSB (Climate Hazards Center). Autenticação server-side via
**conta de serviço** do Google Cloud, projeto `climatga` (nome de exibição
"climaTga" — o ID real do projeto, usado em toda configuração, é sempre
minúsculo: `climatga`). Nível Comunidade, uso não comercial.

**Por quê:** o GEE já mantém o CHIRPS pronto para consulta espacial
(reprojeção, mosaico, catálogo histórico completo desde 1981) sem exigir
que o projeto baixe e processe arquivos raster brutos localmente — a
mesma lógica de "não reinventar o que já existe pronto" usada para os
mapas meteorológicos (Windy) e a malha municipal (IBGE).

**Estratégia de extração:** **média zonal** da precipitação diária sobre o
polígono de cada município — não célula-grade bruta. Para cada dia, o
CHIRPS é reduzido (`reduceRegion` com `Reducer.mean()`) sobre a geometria
inteira do município, gerando **um valor por município por dia**, gravado
em `climate.ChirpsData` (ver mudança de model abaixo). O recorte por
polígono municipal já elimina a necessidade de lidar com célula-grade
individual (~5 km) neste estágio do projeto.

**Escopo:** só os municípios com `ativo=True` em `maps.Municipio` são
processados — hoje Tangará da Serra e Cáceres. O command
(`climate/management/commands/import_chirps.py`) faz
`Municipio.objects.filter(ativo=True)` e itera sobre o resultado; nenhum
nome ou código IBGE de município aparece em lógica condicional no código
— consistente com a decisão de plataforma genérica registrada acima. Os
dois códigos IBGE que aparecem no projeto inteiro (5107958, 5102504)
seguem restritos ao `import_municipios` (que os *marca* como ativos) e à
docstring do `import_chirps` (que só *documenta* o dado, não decide nada
com base nele).

**Mudança em `climate.ChirpsData`:** o model original guardava um ponto de
célula-grade (`latitude`/`longitude`/`geom` Point + FKs opcionais
`station`/`farm`/`owner`, pensado para uso multiusuário futuro). Adicionei
uma FK **nullable** `municipio` (`maps.Municipio`) + `unique_together =
('municipio', 'date')`. Nullable para não descartar o uso original de
célula-grade pontual, caso um dia seja necessário; o `import_chirps`
sempre preenche o campo. `latitude`/`longitude`/`geom` continuam
existindo, mas agora guardam o **centroide do município** (não uma célula
de grade) — o polígono completo mora em `maps.Municipio.geom`, não é
duplicado aqui.

**Idempotência e blocos:** cada registro é gravado por
`update_or_create` usando `(municipio, date)` como chave — rodar o mesmo
período de novo atualiza em vez de duplicar. Períodos longos são
processados em blocos (`--chunk-days`, padrão 365 dias) para respeitar
limites de tempo/memória por requisição do Earth Engine; dentro de cada
bloco, a série diária inteira é reduzida no servidor via
`ImageCollection.map()` — uma única chamada de rede por bloco, não uma
por dia.

**Fora de escopo desta tarefa (Etapa 3.1):** o backfill do histórico
completo do CHIRPS (desde 1981) é a Etapa 3.2, a ser rodada em blocos
depois. Task Celery de atualização automática é a Etapa 3.3. Nenhuma das
duas foi feita aqui — só o mecanismo foi validado, com um período curto
(janeiro/2026).

**Segredos:** a chave da conta de serviço (`secrets/gee-key.json`) não é
versionada (`secrets/` no `.gitignore`). `GEE_PROJECT_ID` e
`GEE_SERVICE_ACCOUNT_KEY_PATH` são lidas de variáveis de ambiente
(`docker-compose.yml` → `geoclima/settings.py`), no mesmo padrão já usado
para as credenciais do Postgres.

## 2026-07-16 — Celery Beat como serviço separado do worker (Etapa 3.3)

**Decisão:** o agendador (`celery beat`) roda em um serviço Docker
**próprio** (`celery_beat`, `docker-compose.yml`), não embutido no
`celery_worker` via `celery worker -B`.

**Por quê:** rodar o beat embutido (`-B`) só é seguro com exatamente 1
worker. Se o `celery_worker` for escalado para múltiplas réplicas no
futuro (`docker compose up --scale celery_worker=3`), cada réplica com
`-B` embutido criaria seu próprio agendador, disparando a mesma tarefa em
triplicidade no mesmo horário. Um serviço `celery_beat` único, independente
da contagem de workers, evita esse problema de origem — é o padrão
recomendado pela documentação do Celery para qualquer ambiente que possa
crescer além de 1 worker.

**Schedule estático em código, não `django-celery-beat`:** o agendamento
(`app.conf.beat_schedule` em `geoclima/celery.py`, usando
`celery.schedules.crontab`) é definido no código, não no banco via o
pacote `django-celery-beat` (que permitiria editar horários pela Django
admin). Não adicionei essa dependência nova porque, por enquanto, só
existe **uma** tarefa periódica fixa (`atualizar_chirps`, 04:00
`America/Cuiaba` todo dia) — não há necessidade real de editar isso em
runtime ainda. Se o projeto precisar de agendamentos configuráveis por
usuário/admin no futuro (Etapa 8/9, por exemplo), reavaliar
`django-celery-beat` nesse momento, não antes.

**Reuso de código, não duplicação:** a task `climate.tasks.atualizar_chirps`
**não reimplementa** a extração CHIRPS/GEE — ela chama o management
command já validado (`import_chirps`, Etapas 3.1/3.2) via
`django.core.management.call_command()`, um por município. A task só
decide **qual período pedir** para cada município (a partir da última
data já gravada em `ChirpsData` até a última data publicada no Earth
Engine); o `reduceRegion`/`ImageCollection.map()` continua existindo em
um único lugar no código (`climate/management/commands/import_chirps.py`).

**Retry:** `autoretry_for=(Exception,)` + `retry_backoff=True` (backoff
exponencial, até 10 min entre tentativas) + `max_retries=5` — declarativo,
sem `self.retry()` manual espalhado pelo código. Falha em um município
não aborta os outros (cada um é tentado independentemente dentro da
mesma execução da task); só se **algum** município falhar é que a task
inteira levanta erro ao final, acionando o retry do Celery — municípios
que já foram atualizados ou que já estavam em dia não são reprocessados
à toa graças ao upsert idempotente do `import_chirps`.

**"Sem dados novos" não é erro:** o CHIRPS tem defasagem de publicação de
~2-3 semanas. É esperado e normal que, na maioria dos dias, a task rode e
não encontre nada para importar (a última data publicada no GEE ainda não
avançou desde a última execução) — isso é logado como `INFO`, não
`WARNING`/`ERROR`, e não conta como falha.

## 2026-07-16 — Autenticação nativa do Django, sem libs de terceiros (Etapa 4)

**Decisão:** login, logout, registro e recuperação de senha usam só
`django.contrib.auth` (views, forms e fluxo de reset de senha nativos).
Nenhuma lib de terceiros (`django-allauth` e afins) foi instalada.

**Por quê:** os requisitos da Etapa 4 (login/senha/registro/recuperação
por e-mail/perfis) são exatamente o que o auth nativo do Django já
resolve, testado e mantido junto do framework. `django-allauth` compensa
quando o projeto precisa de login social (Google/Facebook/etc.),
verificação de e-mail obrigatória mais sofisticada, ou múltiplos métodos
de autenticação — nenhuma dessas necessidades existe hoje. Adicionar a
dependência agora seria complexidade sem benefício correspondente.

**Pendência consciente — verificação de e-mail:** o registro público
**não** exige confirmação de e-mail por link antes de liberar o acesso
(o usuário já é logado automaticamente após se cadastrar). Isso é
aceitável para o estágio atual (desenvolvimento/beta fechado), mas
**precisa ser resolvido antes de qualquer beta público** — nesse
momento, avaliar se o auth nativo do Django é suficiente (dá para
implementar confirmação por e-mail nele mesmo, sem lib nova) ou se vale
a pena reconsiderar `django-allauth` nesse ponto.

**Onde fica o `/painel/`:** a página placeholder pós-login vive no app
`dashboard` (`dashboard/views.py`, `@login_required`), não no `accounts`.
Hoje ela só mostra saudação + perfil; a Etapa 8 vai **estender esta mesma
view/template**, não criar uma nova — assim a URL `/painel/` não muda
quando o dashboard de verdade for construído.

**Papel no cadastro público:** o `CadastroForm` não tem campo de
papel/perfil nenhum (nem oculto) — o `Profile` é criado à parte por um
signal (`post_save` em `User`, `accounts/signals.py`) sempre com
`profile_type="produtor"`. Não é uma validação que exclui só
"administrador" das opções — é a ausência total do campo no formulário,
o que torna a regra estruturalmente impossível de burlar via POST
manipulado. Para mudar o papel de alguém, só pelo admin do Django
(`Profile` embutido na tela do `User`, `accounts/admin.py`) — hoje só o
`admin_demo` (via `seed_demo`) tem `profile_type="admin"`.
