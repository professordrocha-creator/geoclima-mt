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

## 2026-08-23 — Etapa 5: fazendas, talhões e estações

**`Farm.city` (texto livre) trocado por `Farm.municipio` (FK
`maps.Municipio`):** o cadastro de fazenda agora reaproveita o mesmo
seletor Estado→Cidade da Home (`/api/estados/`, `/api/municipios/`) em
vez de o usuário digitar o nome do município à mão. A coluna `city`
continua existindo na tabela (compatibilidade), mas não é mais exposta
no formulário. **Por quê:** desde a Etapa 2.2 já existe uma tabela
oficial e completa de municípios (malha do IBGE) — manter um segundo
conceito de "município" como texto livre duplicaria a ideia e abriria
espaço para erro de digitação/nome divergente do oficial.

**`Farm.municipio` usa `on_delete=models.PROTECT`, não `CASCADE`:**
diferente do padrão do projeto para `owner`/`farm`/`station` (que são
sempre `CASCADE`, porque são dados do próprio usuário). `Municipio` é
dado de referência do IBGE, não dado de usuário — apagar um município
não deve apagar fazendas de usuários silenciosamente. `PROTECT` faz o
banco recusar a exclusão de um `Municipio` enquanto alguma fazenda
apontar pra ele.

**Model novo `Talhao`** (`farms/models.py`) — não existia antes desta
etapa. Ponto georreferenciado simples (mesmo padrão de `Farm`/`Station`),
sem polígono de contorno por enquanto (fica para se for pedido depois).

**Padrão de UI: mapa "clique para marcar" reaproveitado três vezes**
(cadastro de fazenda, talhão, estação) — clicar ou arrastar um marcador
Leaflet preenche campos `latitude`/`longitude` escondidos no form, sem o
usuário digitar coordenadas à mão. No cadastro de fazenda, escolher a
cidade também desenha o contorno do município (reaproveitando
`/api/municipios/<id>/geojson/` já existente da Etapa 2.2) e sugere o
centroide como ponto de partida do marcador.

**Isolamento multiusuário aplicado em toda a Etapa 5:** toda view de
fazenda/talhão/estação busca o objeto já filtrando por `owner=
request.user` na própria query (nunca "depois" de já ter o objeto em
mãos) — tentar acessar/editar a fazenda de outro usuário por URL direta
dá 404, não vazamento de dado nem erro 500. Testado no navegador com dois
usuários diferentes.

**Armadilha descoberta e documentada: `on_delete=CASCADE` do Django é
em nível de ORM, não uma constraint `ON DELETE CASCADE` no Postgres.**
Ao tentar limpar dados de teste com `DELETE FROM farms_farm WHERE
id=...` direto via `psql`, a operação falhou com violação de FK
(`farms_talhao_farm_id_...`), porque o Django cria a constraint no banco
sem `ON DELETE CASCADE` — quem cascateia é o *collector* do Django
(`Farm.objects.filter(id=...).delete()`), executado em Python, não o
banco. **Implicação prática para qualquer
sessão futura:** nunca apagar linhas de `farms_farm` (ou qualquer tabela
com FKs `CASCADE` no model) direto via SQL/`psql` — sempre pelo Django
(shell, admin, ou a própria view), senão a integridade referencial
quebra com erro de constraint em vez de cascatear como o model sugere.

**Outra armadilha descoberta: números do Django dentro de `<script>`
quebram por causa da localização pt-br.** `{{ fazenda.latitude }}`
renderiza `-14,4897` (vírgula, não ponto) porque `LANGUAGE_CODE =
'pt-br'` faz o Django formatar números no estilo brasileiro em qualquer
`{{ variável }}` de template — o que é desejável em texto normal da
página, mas quebra a sintaxe JavaScript quando o valor é embutido dentro
de um `<script>` (`Unexpected number`, testado e confirmado com
Playwright — o formulário de talhão silenciosamente não submetia porque
o clique no mapa não rodava). **Correção aplicada em todos os templates
que embutem coordenadas em JS** (`form_fazenda.html`, `form_talhao.html`,
`form_estacao.html`, `lista_fazendas.html`, `detalhe_fazenda.html`):
`{% load l10n %}` no topo do arquivo e `{% localize off %}...
{% endlocalize %}` envolvendo só os trechos com número dentro de
`<script>`. **Implicação prática:** qualquer template novo que embuta um
`FloatField`/`DecimalField` do model direto num `<script>` precisa do
mesmo tratamento — o sintoma (se esquecer) é sutil: a página carrega
normal, mas cliques/interações JS na área afetada simplesmente não fazem
nada, sem erro visível na tela (só no console do navegador).

## 2026-08-23 — Importação de Shapefile no cadastro de fazenda

**Decisão:** o formulário de cadastro/edição de fazenda ganhou um campo
opcional de upload de shapefile (`.zip` com `.shp`/`.shx`/`.dbf`/`.prj`),
mantendo o clique-no-mapa como alternativa — os dois jeitos convivem, o
usuário escolhe.

- **Polígono da fazenda:** `Farm.poligono` (novo campo `MultiPolygonField`,
  opcional). Quando o shapefile enviado tem feição de polígono, ela vira
  o contorno da propriedade, e a localização (`geom`/`latitude`/
  `longitude`) passa a ser o **centroide** desse polígono — o shapefile
  manda mais que um clique manual no mapa, se os dois forem enviados
  juntos. Se houver mais de uma feição de polígono no arquivo (ou em
  vários `.shp` dentro do mesmo `.zip`), todas são **unidas** num
  `MultiPolygon` só — não escolhe "a maior" e descarta o resto, porque
  uma fazenda pode ter parcelas não-contíguas.
- **Pontos viram estações automaticamente:** cada feição de ponto no
  shapefile cria uma `Station` (tipo "Manual", nome lido de uma coluna
  de atributo tipo `nome`/`name` se existir, senão "Estação importada
  N"). O usuário edita nome/tipo depois pela tela normal de estação —
  não pedimos esses dados no momento do upload, pra não complicar o
  fluxo de importação.
- **Reprojeção automática:** lê o `.prj` de cada shapefile (mesmo
  tratamento do `import_municipios`, Etapa 2.2) e reprojeta pra WGS84.
  Sem `.prj`, assume que as coordenadas já estão em WGS84 e avisa via
  `messages.warning` — não tem como saber a projeção de origem sem o
  arquivo.
- **Contorno usado como referência ao cadastrar estação:** endpoint
  `farms:poligono_fazenda_json` (`/painel/fazendas/<id>/poligono.json`,
  restrito ao dono) devolve o polígono da fazenda escolhida; o mapa de
  cadastro de estação desenha isso como camada de fundo ao trocar a
  fazenda no `<select>` — só visual, não obrigatório, não limita onde a
  estação pode ser clicada.
- **Editar fazenda sem reenviar shapefile não apaga o contorno:** a view
  guarda os valores anteriores de `latitude`/`longitude`/`geom`/
  `poligono` antes do form processar a edição, e só os sobrescreve se
  vier shapefile novo ou clique novo no mapa — senão a edição de
  qualquer outro campo (nome, área, observações) apagaria a localização
  sem querer.

**Testado com shapefile real** (gerado via `ogr2ogr` para o teste, com
1 polígono + 2 pontos nomeados): fazenda criada sem nenhum clique no
mapa, contorno desenhado corretamente no detalhe da fazenda, 2 estações
criadas automaticamente com os nomes do shapefile, contorno aparecendo
como referência ao cadastrar uma 3ª estação manualmente.

## 2026-08-23 — Cultura agrícola: campo único mantido de propósito (não é esquecimento)

**Decisão:** `Farm.crop`/`Talhao.crop` continuam sendo um único
`CharField` cada — **não** viraram um model de calendário de plantio
(sucessão de safra/safrinha), apesar de ter sido levantado que uma
fazenda real pode ter mais de uma cultura por ano na mesma área (ex.:
soja na 1ª safra, milho ou algodão na safrinha).

**Por quê ficou assim por enquanto:** o PDF de requisitos (Etapa 5) só
pede um campo simples de "cultura agrícola" por fazenda — é
exatamente o que existe. Modelar sucessão de cultivo de verdade (um
model novo tipo `Cultivo`/`Safra`, com `talhão` + `cultura` + datas de
plantio/colheita) é um aumento de escopo real: precisa decidir se fica
no talhão ou na fazenda, se precisa de datas ou só rótulo de
safra, e principalmente **para quê** vai servir — a resposta mais
provável é alimentar insights futuros (Etapa 9: "janela favorável de
plantio", "necessidade de irrigação", que cruzam cultura × data ×
clima). Faz mais sentido desenhar isso junto com a Etapa 9, quando o
"para quê" estiver claro, do que adivinhar a estrutura agora.

**O que já existe, mesmo sem essa modelagem:** como `Talhao.crop` é
independente de `Farm.crop`, já dá pra ter culturas diferentes em
talhões diferentes da mesma fazenda hoje — só a sucessão **no tempo**,
na mesma área, é que não é representável ainda. Se precisar registrar
mais de uma cultura por área antes da Etapa 9 chegar, o caminho de
menor esforço é digitar as duas no texto livre (ex.: "Soja / Milho
Safrinha") — sem estrutura, mas sem inventar um model que pode não
bater com o que a Etapa 9 vai precisar de verdade.

## 2026-08-23 — Lição aprendida: nunca rodar `.delete()` sem filtro por dono

**O que aconteceu:** ao limpar dados de teste do Playwright depois de
validar a importação de shapefile, rodei `Farm.objects.all().delete()`
— **sem filtrar por usuário** — pensando que só existiam fazendas de
teste no banco. Isso apagou também a fazenda real do usuário
("fazenda Rocha") e o talhão dela ("talha 1"), cadastrados por ele
antes desta sessão. Não havia backup nem WAL archiving configurados
(`archive_mode = off`) — **os dados foram perdidos, sem recuperação
possível**. Registrado aqui como incidente real, não hipotético.

**Regra a partir de agora, para qualquer sessão futura (humana ou
Claude) que precisar limpar dado de teste neste projeto:**
- **Nunca** rodar `.delete()` (ou `DELETE` via SQL) sem filtro
  explícito por `owner` — mesmo "tendo certeza" de que só existe dado
  de teste no banco. Checar antes com uma query de leitura
  (`.values('owner__username')` ou `SELECT DISTINCT owner_id`) e só
  então apagar filtrando pelos usuários de teste conhecidos
  (`joao.produtor`, `novo.teste`), nunca `.all()`.
- Antes de qualquer limpeza "definitiva", considerar `SELECT`/print dos
  dados que vão ser apagados primeiro (mesmo que não vá salvar em
  lugar nenhum) — pelo menos fica registrado na transcrição da sessão
  caso precise reconstruir manualmente depois, como teve que ser feito
  aqui.
- Se algum dia o projeto for além do ambiente de desenvolvimento local
  (dados reais no banco valendo de verdade), configurar backup/dump
  regular antes disso — hoje não existe nenhum, nem manual nem
  automático.

## 2026-08-23 — Etapa 6: lançamento manual e importação de CSV/Excel

**Model:** `RainfallData` ganhou `time` (horário, opcional) e `notes`
(observações, opcional) — o PDF pedia os dois pro lançamento manual
("chuva diária; horário; observações; anotações de campo") e não
existiam no model original. Migration `climate.0003`.

**Dependência nova:** `openpyxl` (leitura de `.xlsx`) — decisão
explícita do usuário (perguntei antes: só CSV agora, ou CSV+Excel
juntos com a lib nova; escolheu os dois juntos). Lib leve, padrão de
mercado pra Excel em Python, sem trazer pandas/numpy como transitiva.

**Parser único pra CSV e Excel** (`climate/data_import.py`): detecta
colunas pelo **nome do cabeçalho**, case-insensitive, aceita variações
comuns em português/inglês (`data`/`date`, `valor`/`chuva`/
`precipitacao`, `horario`/`hora`, `observacoes`/`obs`) — não exige um
template de planilha rígido, porque cada produtor exporta do jeito que
o pluviômetro/estação dele já fornece. Datas aceitas em `AAAA-MM-DD` ou
`DD/MM/AAAA`; no Excel, células já formatadas como data/hora são lidas
diretamente (sem precisar re-parsear string).

**Idempotência:** tanto o lançamento manual quanto a importação de
arquivo usam `update_or_create` por `(station, date, source_type)` —
mesma chave que já era `unique_together` no model desde antes desta
etapa. Relançar o mesmo dia/estação ou reimportar o mesmo arquivo
atualiza em vez de duplicar. Testado explicitamente: reenviar o mesmo
lançamento manual duas vezes resultou em 1 registro (atualizado), não 2.

**Origem do dado (`source_type`) não distingue CSV de Excel:** os dois
formatos de importação gravam com `source_type='imported_csv'` — o
model (e o PDF, na lista de `source_type`) só prevê um valor genérico
pra "dado importado de arquivo", não um por formato. Não criamos um
`imported_excel` novo pra não divergir do schema original sem motivo.

**Armadilha nova encontrada e corrigida: `<input type="date">`/
`type="time"` com `LANGUAGE_CODE=pt-br`.** Ao editar um lançamento
existente, o campo de data ficava **vazio** — o Django preenche o
`value` do widget no formato localizado (`DD/MM/AAAA`), mas o HTML5
`<input type="date">` só aceita `AAAA-MM-DD` nesse atributo; o
navegador rejeita o valor inválido silenciosamente (sem erro nenhum,
nem do servidor nem do JS) e o campo nasce vazio. Como o campo é
obrigatório, a validação nativa do navegador bloqueava o submit sem
nem chegar no Django — sintoma parecido com a armadilha do `{%
localize off %}` (Etapa 5), mas em outra camada (widget de formulário,
não `<script>` inline). **Correção:** `forms.DateInput(attrs={"type":
"date"}, format="%Y-%m-%d")` e o mesmo pra `TimeInput` com `"%H:%M"` —
o parâmetro `format=` do widget força o formato ISO independente da
localização. **Implicação prática:** qualquer `DateField`/`TimeField`
novo usado com `<input type="date">`/`type="time"` neste projeto
precisa desse `format=` explícito no widget, só descoberto testando a
edição de verdade no navegador (o cadastro/criação não expõe o bug,
porque começa vazio de qualquer jeito — só apareceu ao editar um
registro já existente).

## 2026-08-23 — Etapa 7.1: cálculo do SPI

**Fonte do dado — só CHIRPS, não `RainfallData`:** o SPI precisa de
uma média/desvio-padrão climatológicos confiáveis, o que exige décadas
de histórico na mesma janela do calendário. Só `climate.ChirpsData`
tem isso (44 anos); o dado manual/importado do usuário
(`RainfallData`) ainda tem só dias/semanas de histórico — não é
estatisticamente utilizável pra isso ainda. **Consequência direta,
confirmada com o usuário antes de codar:** o SPI só é calculável hoje
pra fazendas/estações em municípios com `ativo=True` (Tangará da Serra
e Cáceres) — não por nome/código de município citado em lugar nenhum
do código (`spi/services.py` e `calcular_spi` iteram
`Municipio.objects.filter(ativo=True)` genericamente), mas porque só
esses dois têm CHIRPS importado. **Isso já está pronto pra crescer
sozinho**: quando outro município virar `ativo=True` e tiver o
backfill do CHIRPS rodado (mecanismo já existente desde a Etapa 3,
reaproveitável sem nenhum código novo), o SPI passa a funcionar lá
automaticamente.

**Fórmula seguida ao pé da letra do PDF:** `SPI = (Xi - X̄) / σ` — um
z-score simples, **não** o método McKee "oficial" (que ajusta uma
distribuição Gama antes de padronizar, mais complexo e exigiria
scipy). O PDF dá exatamente essa fórmula simples, então é isso que foi
implementado — não substituí por um método mais sofisticado que não
foi pedido.

**Limiares de classificação não vêm no PDF** (só os 6 nomes das
categorias) — usei os limiares padrão da literatura (McKee et al.
1993: ±1, ±1.5, ±2), fundindo "moderadamente úmido"/"moderadamente
seco" nas categorias vizinhas pra caber exatamente nas 6 que o model
já define (`extremamente_umido` ≥2,0 · `muito_umido` ≥1,0 ·
`normal` entre -1,0 e 1,0 · `seca_moderada` ≥-1,5 · `seca_severa`
≥-2,0 · `seca_extrema` abaixo disso). Documentando aqui porque é uma
escolha interpretativa, não algo explicitado no PDF.

**Agrupamento por mês do calendário:** a distribuição de referência de
cada valor de SPI é "todos os SPI-N terminando no mesmo mês do
calendário, em todos os anos" (ex.: todos os SPI-3 de março, de
1983 a 2026) — não a série inteira misturada. É assim que o SPI
padrão funciona (sazonalidade importa: a "normalidade" de março não é
a mesma de agosto). `MINIMO_ANOS_HISTORICO = 10`: exige pelo menos 10
anos de dado no mesmo mês antes de calcular — limiar conservador
deste projeto, não uma norma oficial, pra evitar SPI estatisticamente
frágil com poucos anos de amostra.

**`SpiResult.station` continua obrigatório (sem migration nesta
sub-etapa):** o SPI é regional (por município), mas o model já exige
FK `station`. Em vez de mudar o schema agora, o comando grava **o
mesmo valor de SPI pra cada estação** que o usuário tem numa fazenda
daquele município — redundante se o usuário tiver 2+ estações na
mesma fazenda (mesmo valor duplicado por estação), mas evita mais uma
migration nesta etapa. Se isso incomodar na prática, o ajuste natural
seria `station` virar opcional e a unicidade passar a ser por `farm`,
não por `station` — fica registrado aqui como possível revisão futura,
não fiz agora pra não acumular mudança de schema sem necessidade
comprovada.

**Sem view/dashboard novo:** o resultado aparece só como um cartão
pequeno ("SPI atual") na página de detalhe da fazenda
(`farms/detalhe_fazenda.html`) — não criei uma tela dedicada de SPI,
porque isso é papel da Etapa 8 (dashboard). Mesmo padrão já usado no
`/painel/` placeholder da Etapa 4: entrega o mínimo útil agora, sem
antecipar o que a etapa de verdade vai construir.

**Testado com dado real do usuário** (fazenda "fazenda Rocha", Tangará
da Serra, 2 estações): 3.246 registros gravados (545+542+536 meses ×
2 estações), média dos z-scores ≈ 0,000 em todas as escalas
(confirma a padronização correta), distribuição de classificação
plausível (maioria "normal", caudas decrescentes nos extremos —
compatível com uma distribuição aproximadamente normal). Idempotência
confirmada (rerun: 0 novos, todos atualizados, total não mudou).

## 2026-08-23 — Etapa 7.2: validação estatística CHIRPS × dado local

**Model novo `climate.ChirpsValidation`** — não existia antes.
`OneToOneField(Station)` de propósito: é o retrato **mais recente** da
validação daquela estação, não uma série temporal — cada
`validar_chirps` novo substitui o resultado anterior. Diferente do
`SpiResult` (série mensal, um valor por mês) porque validação estatística
não tem essa dimensão temporal natural — o que importa é "com o dado que
existe hoje, quão bem o CHIRPS bate", e isso muda a cada novo lançamento,
não por mês do calendário.

**Métricas implementadas exatamente como o PDF pede**: R², RMSE, MAE,
MBE, índice d, índice c. Fórmulas:
- RMSE/MAE/MBE: diretas, sem ambiguidade.
- **Índice d (Willmott, 1981)**: `1 - [Σ(P-O)²]/[Σ(|P-Ō|+|O-Ō|)²]`,
  P=CHIRPS, O=local, Ō=média do local. Fórmula padrão, sem
  interpretação livre.
- **R²**: correlação de Pearson ao quadrado (`r²`), usando
  `statistics.correlation` (nativo do Python 3.10+, sem dependência
  nova).
- **Índice c (Camargo & Sentelhas, 1997)**: `c = r × d` (não r² × d —
  usa o `r` sem elevar ao quadrado). É o índice de desempenho padrão
  da agrometeorologia brasileira; o PDF não detalha a fórmula, mas
  "índice c" nesse contexto (ao lado de "índice d" de Willmott) é
  inequivocamente essa referência. Classificação por faixas também
  do mesmo padrão (Ótimo >0,85 · Muito bom 0,76–0,85 · Bom 0,66–0,75 ·
  Mediano 0,61–0,65 · Sofrível 0,51–0,60 · Mau 0,41–0,50 · Péssimo
  ≤0,40) — não vem no PDF, documentando aqui pela mesma razão dos
  limiares do SPI.

**Comparação por dia pareado, não por período agregado:** um par
(CHIRPS, local) só existe se as duas fontes tiverem valor pro
**mesmo dia**. `MINIMO_PARES = 3` — abaixo disso, correlação e
desvio-padrão não são estatisticamente confiáveis (na prática, com só
1-2 pontos, o comando reporta "dado insuficiente" em vez de gerar um
número enganoso).

**Mesma restrição de dado do SPI (Etapa 7.1), pelo mesmo motivo:** só
existe CHIRPS pra municípios `ativo=True` — uma estação fora de
Tangará da Serra/Cáceres não tem com o que comparar ainda, mesmo já
tendo dado local lançado. Não é condição de código (o comando não cita
município nenhum), é ausência de dado.

**Testado com dado sintético mas matematicamente realista** (não dado
aleatório): peguei 10 dias reais de CHIRPS de Tangará da Serra e criei
"dado local" = `chirps × 1,05 + 0,5` (transformação linear com viés
pequeno, simulando uma estação real bem correlacionada mas não
idêntica ao CHIRPS). Resultado: R²=1,000 (esperado — transformação
linear tem correlação perfeita), MBE=-0,79mm (negativo, porque o
"local" simulado foi sistematicamente mais alto que o CHIRPS — bate
com o sinal esperado: MBE = CHIRPS-local), índice c=0,995 ("ótimo") —
todos os números batem exatamente com o que a matemática prevê pra
esse cenário construído, confirmando a implementação. Dados de teste
removidos depois, filtrados por `owner=joao.produtor` — dado real do
usuário (`daniel`, 1 lançamento manual de 23/08/2026, sem par de
CHIRPS ainda por ser data muito recente) conferido intacto antes/depois.

## 2026-08-23 — Etapa 7.3: detecção de inconsistências

**Reaproveitado `alerts.Alert` em vez de criar model novo** — o
próprio PDF, na seção "Detecção de Inconsistências", já fala em
"gerar alertas automáticos". Adicionado um tipo novo,
`inconsistency` (`alerts.migrations.0002`), sem tocar em mais nada da
Etapa 9 (isso significa que o app `alerts` deixou de estar 100%
"schema sem uso" antes da Etapa 9 formalmente começar, mas é o próprio
PDF que pede o mesmo mecanismo pros dois casos).

**As 4 checagens do PDF, todas sobre `RainfallData` (dado local, não
CHIRPS):**
- **Chuva negativa**: `value < 0`. Também **bloqueada na entrada** do
  formulário de lançamento manual (`LancamentoManualForm.clean_value`)
  — pega o erro de digitação na hora, não só detecta depois. CSV/Excel
  importado continua aceitando (pra não descartar dado silenciosamente
  no meio de uma importação em lote) e é pego pela detecção depois.
- **Valores extremos**: acima de `LIMITE_VALOR_EXTREMO_MM = 200` —
  limiar conservador, não um valor fisicamente impossível (chuvas de
  200+ mm/dia já ocorreram em eventos raros em MT); é "revise isso",
  não "isso está errado".
- **Duplicados**: interpretado como **mesmo valor exato repetido em
  dias consecutivos** (`MINIMO_DIAS_REPETIDOS = 3`) — sinal clássico de
  sensor travado ou erro de cópia em lançamento manual. Não confundir
  com duplicata de registro (isso já é impedido no banco desde a Etapa
  6 pelo `unique_together = ('date', 'station', 'source_type')`).
- **Falhas temporais**: gap de `GAP_MINIMO_FALHA_TEMPORAL_DIAS = 5`
  dias ou mais entre dois lançamentos consecutivos da mesma estação.

**Idempotência via `get_or_create` por `(station, alert_type,
message)`** — mesma inconsistência não duplica alerta ao rodar de
novo. Se o dado mudar (ex.: gap aumentar), a mensagem muda e um alerta
novo é criado; o antigo **não** é desativado automaticamente —
gerenciar o ciclo de vida completo do alerta (marcar como resolvido,
etc.) fica pra Etapa 9, não é escopo desta sub-etapa.

**Testado com cenário sintético cobrindo as 4 checagens ao mesmo
tempo** (chuva negativa, valor extremo, 3 dias com valor repetido, gap
de 15 dias) — as 4 mensagens "Possível inconsistência detectada: ..."
(texto exato do PDF) apareceram corretamente, idempotência confirmada
(rerun: 0 novos, 4 já existentes). Bloqueio de chuva negativa no
formulário de lançamento manual também testado no navegador (submit
bloqueado, mensagem de erro exibida). Dados de teste limpos filtrados
por `owner=joao.produtor`.

**Armadilha de autoreload do Django — 3ª ocorrência nesta sessão.**
Desta vez não foi arquivo/pasta nova, foi só uma edição num arquivo já
existente (`farms/views.py`, adicionando `from alerts.models import
Alert`) — mesmo assim o processo continuou rodando com uma versão
antiga em memória (`NameError: name 'Alert' is not defined`, mesmo com
o arquivo em disco correto), só resolveu com `docker compose restart
web`. Como já são 3 ocorrências na mesma sessão de trabalho, fica
registrado como comportamento a **esperar, não mais investigar**: depois
de qualquer edição estrutural em `views.py` (novo import de outro app,
nova função), testar no navegador primeiro; se der `NameError`/
`TemplateDoesNotExist`/500 inesperado com o código aparentemente
correto, ir direto pro `docker compose restart web` em vez de
depurar mais.

## 2026-08-23 — Etapa 7.4: correção local / calibração regional do CHIRPS

**Contexto:** última sub-etapa da Etapa 7. O PDF pede "calibração
regional; correção de viés; ajuste local do CHIRPS", com um exemplo
concreto: "CHIRPS estimou 100 mm; estação local registrou 112 mm;
sistema aprende diferença regional".

**Decisão: correção aditiva de viés, reaproveitando o MBE já calculado
pela Etapa 7.2, sem estatística nova.** O exemplo do PDF é literalmente
uma correção aditiva (100 → 112 = +12), e `climate/validation.py` já
calcula exatamente essa diferença média (MBE = média(chirps − local))
desde a 7.2. Em vez de introduzir um segundo método de calibração
(ex.: regressão linear completa com slope/intercept), a correção é:

```
valor_corrigido = valor_chirps − mbe
```

(subtrair o MBE porque MBE é `chirps − local`; se o CHIRPS
sub-estimava, MBE é negativo, e subtrair um negativo soma o viés de
volta — bate com o exemplo do PDF). Resultado sempre limitado a `>= 0`
(chuva não é negativa).

**Decisão: nada persistido, tudo calculado on-the-fly.** Como a
`ChirpsValidation` (Etapa 7.2) já é "sempre o estado mais recente, não
histórico", a correção segue o mesmo espírito: `climate/correction.py`
lê o MBE mais atual da `ChirpsValidation` da estação e aplica sobre o
`ChirpsData` bruto do município (que continua intocado) toda vez que a
página é carregada. Não existe model novo, não existe management
command novo — seria persistência especulativa sem um consumidor
concreto ainda (a correção não realimenta SPI nem é usada em nenhum
outro lugar do sistema por enquanto).

**Fora do escopo desta sub-etapa, explicitamente:** a correção **não**
realimenta o cálculo do SPI (Etapa 7.1) — o SPI é calculado a partir do
CHIRPS bruto por município (nível regional), enquanto o MBE é por
estação (nível de uma estação específica dentro do município);
misturar os dois exigiria decidir como agregar vários MBEs de estações
diferentes num único ajuste municipal, o que não está pedido no PDF e
fica em aberto para se for necessário depois.

**Pré-requisito:** só existe correção para uma estação que já tenha
`ChirpsValidation` calculada (`n_pares >= MINIMO_PARES = 3`, mesma
restrição da 7.2) — sem isso não há viés confiável pra aplicar. Mesma
limitação de DADO da 7.1/7.2/7.3: só funciona hoje pra municípios
`ativo=True` com dado local suficiente pareado com CHIRPS.

**Testado com cenário sintético matematicamente controlado:** 10 dias
reais de CHIRPS de Tangará da Serra, "dado local" = `chirps + 10`
(viés constante conhecido). `validar_chirps` calculou **MBE=-10,00mm**
exatamente como esperado (R²=1,000, correlação perfeita de um deslocamento
constante). A série corrigida (`serie_chirps_corrigida`) reproduziu o
valor local original em todos os 10 dias (`corrigido = bruto + 10 =
local`), confirmando a fórmula, não só que "rodou sem erro". Card "CHIRPS
Corrigido (Calibração Local)" testado no navegador (Playwright), sem
erros de console. Dados de teste limpos filtrados por
`owner=joao.produtor`, fazenda real do `daniel` (id=8, "fazenda Rocha")
conferida intacta antes e depois.

**Etapa 7 (SPI) está completa: 7.1, 7.2, 7.3 e 7.4 concluídas.**

## 2026-08-23 — Etapa 8.1: estrutura do dashboard privado

**Contexto:** primeira sub-etapa da Etapa 8. O PDF pede um dashboard
privado por usuário com 8 itens (chuva atual, acumulados, SPI,
tendências, gráficos, mapas, comparação CHIRPS×local, previsão
climática) — grande demais pra uma tarefa só, então quebrado em
sub-etapas (confirmado com o usuário via pergunta direta, mesmo padrão
da Etapa 3/7): 8.1 chuva atual/acumulados/série, 8.2 SPI/comparação
CHIRPS×local, 8.3 mapa geral/previsão.

**Decisão: agregação por FAZENDA, não por usuário nem por estação.**
Um usuário pode ter várias fazendas em municípios diferentes — somar
tudo num único número por usuário esconderia informação útil (chuva
em Cáceres não é a mesma coisa que chuva em Tangará da Serra). Por
estação seria granular demais e já existe em
`farms/detalhe_fazenda.html`. O dashboard ganhou um seletor de fazenda
(`?fazenda=<id>`, querystring simples, sem sessão) — a mesma
view/rota da Etapa 4 (`/painel/`) foi **estendida**, não criada uma
rota nova, decisão já tomada nessa etapa.

**Decisão: dado local e CHIRPS nunca somados juntos no mesmo número.**
"Chuva atual" prioriza dado local (mais preciso) e só cai pro CHIRPS
se não houver nenhum lançamento local ainda. "Acumulados"/"série"
mostram os dois **lado a lado**, cada um identificado — inclusive nos
acumulados, se uma janela tiver QUALQUER dado local, mostra só o total
local dessa janela (não soma com CHIRPS), mesmo que o CHIRPS cubra
mais dias dentro da mesma janela. É uma simplificação deliberada: somar
uma medição de campo com uma estimativa de satélite no mesmo total
mm produziria um número que parece mais preciso do que é. A
UI deixa isso explícito ("usa CHIRPS só nas janelas sem lançamento
local").

**Decisão: Chart.js via CDN, sem dependência Python nova.** Primeira
lib de gráfico do projeto — escolhida por ser leve, sem build step,
carregada via `<script src="cdn.jsdelivr.net/...">` no
`extra_scripts` da página, mesmo padrão já usado pro Leaflet
(`unpkg.com`). Nenhuma entrada nova em `requirements.txt`.

**Nenhum model novo.** As três funções de `dashboard/services.py` são
puramente agregações on-the-fly sobre `climate.RainfallData`/
`ChirpsData` já existentes — mesmo espírito de `climate/correction.py`
(Etapa 7.4): sem persistência especulativa sem um consumidor concreto.

**Armadilha de localização (pt-br) de novo, desta vez em dado
JSON-like embutido num `<script>` pro Chart.js** — mesma classe do bug
da Etapa 5 (`{{ float }}` vira `12,5` em vez de `12.5` dentro de
`<script>`). `{% load l10n %}{% localize off %}` aplicado de novo em
`dashboard/painel.html` ao montar o array `serieChuva` em JS. Não é
uma ocorrência nova do bug, é a mesma lição da Etapa 5 sendo aplicada
proativamente desta vez (não descoberta por erro em produção).

**Testado com fazenda real do usuário em modo só-leitura** (chamadas
diretas de `dashboard/services.py` no shell, sem nenhum `.save()`/
`.delete()`) — evita repetir qualquer risco de escrita acidental em
dado real, já que o incidente de Etapa 5 ensinou a ser mais cauteloso
perto de dado do `daniel`. Cenários de escrita (fallback CHIRPS,
gráfico renderizando de fato — pixels no canvas conferidos, não só
"sem erro de JS") testados só na fazenda sintética temporária
(`joao.produtor`), removida depois, filtrada por owner.

## 2026-08-23 — Etapa 8.2: tendência do SPI + comparação CHIRPS × local em gráfico

**Contexto:** segunda sub-etapa do dashboard (8.1 → 8.2 direto, "sim"
do usuário). Faltavam 2 dos 8 itens do PDF: tendência de SPI e
comparação CHIRPS×local — os dois já existem como CARTÕES NUMÉRICOS
no detalhe da fazenda (SPI atual, métricas de validação da Etapa 7.2),
mas nunca como gráfico, nem agregados na visão do dashboard.

**Decisão: SPI representado por UMA linha por data (colunas SPI-3/6/
12), não uma lista separada por escala.** Motivo técnico real, não
estético: SPI-12 exige 12 meses de janela móvel antes do primeiro
valor possível, então a série de SPI-12 começa bem depois da de SPI-3
— têm tamanhos diferentes. Se cada escala fosse uma lista própria e o
gráfico usasse os rótulos (datas) da série mais longa pra todas,
Chart.js alinha datasets por **índice de array**, não por valor de
data — as datas da série mais curta ficariam deslocadas pra trás,
mostrando o SPI-12 na data errada. Resolvido fazendo
`serie_spi()` devolver uma lista por data com `spi_3`/`spi_6`/`spi_12`
(`None` na escala que ainda não tem valor), e usando `spanGaps: true`
no Chart.js pra pular os `None` sem quebrar a linha visualmente. Esse
é o tipo de bug que só aparece olhando o gráfico renderizado, não em
`manage.py check` nem em teste que só confere "não deu erro" — vale
lembrar disso em qualquer gráfico futuro que combine séries de
tamanhos diferentes.

**Decisão: gráfico de dispersão (scatter) pra comparação CHIRPS×local,
com linha de referência y=x.** É o tipo de gráfico padrão em
validação agrometeorológica (o mesmo conceito por trás do índice d/c
já calculados na Etapa 7.2) — cada ponto é um dia, quanto mais perto
da diagonal "CHIRPS = local", melhor a concordância. Reaproveita
`climate.validation.pares_chirps_local(station)` sem recalcular nada;
uma série por estação (cor diferente), pra fazenda com mais de uma
estação validada não misturar os pontos de estações diferentes num
mesmo blob sem explicação.

**Nenhum model novo, nenhuma estatística nova** — mesmo espírito das
sub-etapas anteriores da Etapa 8/7: `dashboard/services.py` só
reorganiza dado que `SpiResult` (7.1) e `ChirpsValidation`/
`pares_chirps_local` (7.2) já calculam.

**Testado com fazenda sintética temporária** (`joao.produtor`,
removida depois): `calcular_spi` recalculado pro município inteiro
(545/542/536 meses por escala — idempotente, `update_or_create`, não
apagou nada, só atualizou os mesmos valores determinísticos vindos do
CHIRPS, inclusive das estações reais do `daniel` no mesmo município)
e `validar_chirps` pra estação de teste (R²=1,000, MBE=-5,00mm com
viés sintético conhecido de +5mm). Os dois gráficos conferidos no
navegador via Playwright com **pixels de fato desenhados no canvas**,
zero erros de console. Também testado em modo leitura contra a
fazenda real do usuário (`daniel`, id=8): `serie_spi` devolveu 119
meses corretamente (SPI-12 preenchido só a partir de quando tinha
12 meses de histórico, como esperado); `comparacao_chirps_local`
devolveu lista vazia (nenhuma estação real do usuário tem
`ChirpsValidation` calculada ainda) sem erro — tratado corretamente
pelo template (mensagem "sem dado suficiente").

## 2026-08-23 — Etapa 8.3: mapa geral + previsão climática — Etapa 8 completa

**Contexto:** terceira e última sub-etapa do dashboard. Os 2 itens que
faltavam do PDF ("Dashboard Privado": mapas, previsão climática) eram
os únicos dos 8 que não reaproveitavam nenhum dado já calculado nas
Etapas 7/3 — mapa é só posição (`Farm.latitude`/`longitude`, já
existe desde a Etapa 5) e previsão é uma API externa em tempo real
(Open-Meteo), não um dado do banco.

**Decisão: mapa mostra TODAS as fazendas do usuário, não só a
selecionada no dropdown.** Diferente dos cartões de chuva/SPI/
comparação (que são por fazenda, dependem do seletor), o mapa é
naturalmente uma visão de conjunto — é o único jeito de ver "onde
estão minhas fazendas" de uma vez, coisa que não dá pra fazer olhando
uma fazenda de cada vez em `farms/detalhe_fazenda.html`. A fazenda
atualmente selecionada no dropdown ganha um tooltip fixo (nome sempre
visível), as outras só popup ao clicar — dá pra identificar qual é
qual sem abrir todos os popups.

**Decisão: previsão climática é fetch client-side, direto pra
Open-Meteo, sem passar pelo backend Django.** Mesmo padrão já usado na
Home pública desde 2026-06-19 (ver entrada de 19/06 em HISTORICO.md) —
o backend nunca fez proxy dessa chamada, é sempre o navegador do
usuário que busca direto. Manter consistência em vez de inventar um
segundo padrão (endpoint Django fazendo proxy) só porque agora é uma
página logada.

**Decisão: mapeamento de `weather_code` DUPLICADO e REDUZIDO, não
importado/reaproveitado do template da Home.** `core/index.html` já
tem um comentário explícito dizendo que esse mapeamento é "duplicado
para frontend e backend por segurança" — não existe reaproveitamento
de JS entre templates Django sem um bundler (não tem um no projeto), e
a Home já tinha estabelecido esse padrão de duplicação como aceitável.
O card do dashboard é compacto (ícone + condição + min/max + chuva),
não precisa dos ~25 códigos da Home inteira — só um subconjunto dos
mais comuns (~15 códigos), com um fallback "—"/interrogação pros
raros que não estão na lista reduzida.

**Nenhuma mudança em `dashboard/views.py`/`services.py`** — os dois
itens desta sub-etapa não precisaram de nenhuma agregação de banco
nova (mapa usa campos que já vinham no `fazendas` do contexto desde a
8.1; previsão nem toca o backend). Só `dashboard/painel.html` mudou.

**Testado com 2 fazendas sintéticas temporárias** (`joao.produtor`,
municípios diferentes — Tangará da Serra e Cáceres — removidas
depois): mapa renderizado com **2 marcadores confirmados** via
Playwright (`document.querySelectorAll('.leaflet-marker-icon')`),
`fitBounds` cobrindo as duas. Previsão testada com uma **chamada real
à Open-Meteo** (não mockada) — resposta com temperatura atual,
condição e 5 dias de previsão renderizados corretamente no card. Zero
erros de console. Fazenda real do usuário (`daniel`, id=8) conferida
intacta antes e depois.

**Etapa 8 (dashboard privado) está completa: 8.1, 8.2 e 8.3
concluídas.**

## 2026-08-23 — Etapa 9.1: alertas climáticos automáticos (seca, excesso de chuva, risco hídrico, anomalia)

**Contexto:** primeira sub-etapa da Etapa 9, confirmada com o usuário
via pergunta direta (quebrar em 9.1 alertas + 9.2 insights, deixar
notificações — "futuro" no PDF — de fora por enquanto). `alerts.Alert`
já tinha os 4 tipos no schema desde a Etapa 1, mas nenhuma lógica de
geração — só o 5º tipo (`inconsistency`) ganhou lógica, na Etapa 7.3,
mas esse é sobre qualidade do DADO, não sobre o CLIMA em si.

**Decisão central: cada um dos 4 tipos usa uma combinação DIFERENTE
de escala do SPI (3/6/12) + faixa de severidade, pra não duplicar o
mesmo sinal em dois alertas diferentes.** O PDF não especifica o
critério técnico de cada alerta, só os nomes — decisão de projeto
necessária antes de codar. Critério escolhido, baseado em uso comum
de SPI em agrometeorologia (SPI-3 pra impacto agrícola de curto prazo,
SPI-6 pra planejamento de reservatório/irrigação de médio prazo, SPI-12
pra desvio climático estrutural de longo prazo):

| Alerta | Escala | Classificações que disparam |
|---|---|---|
| Seca (`drought`) | SPI-3 | seca_moderada, seca_severa, seca_extrema |
| Excesso de chuva (`excess_rain`) | SPI-3 | muito_umido, extremamente_umido |
| Risco hídrico (`water_risk`) | SPI-6 | seca_severa, seca_extrema |
| Anomalia climática (`anomaly`) | SPI-12 | seca_extrema, extremamente_umido |

Seca e excesso de chuva usam a MESMA escala (SPI-3) porque são lados
opostos da mesma distribuição (seco vs. úmido) — não há duplicação de
sinal, são mutuamente exclusivos por definição (uma estação nunca está
nas duas classificações ao mesmo tempo). Risco hídrico usa uma escala
mais longa (SPI-6) e um limiar mais severo (só os 2 piores níveis) —
representa uma condição mais grave e mais estrutural do que a "seca"
de curto prazo. Anomalia usa a escala mais longa (SPI-12) e só os
extremos absolutos dos dois lados — um desvio raro e persistente, não
uma oscilação normal de estação chuvosa/seca do Centro-Oeste.

**Decisão: olhar só o SpiResult MAIS RECENTE de cada estação, não o
histórico inteiro.** `SpiResult` guarda 500+ meses de histórico por
estação (Etapa 7.1); gerar um alerta pra cada mês histórico que já
esteve em seca não faz sentido — alerta é sobre a condição ATUAL.
Rodar `detectar_alertas_climaticos` depois de cada `calcular_spi`
(mensal, quando o CHIRPS atualizar) é o fluxo esperado: se a condição
mudar de mês pra mês, a mensagem muda (data/valor diferentes) e um
`Alert` novo é criado — o antigo fica no histórico (mesma decisão de
não desativar automaticamente já tomada na Etapa 7.3).

**Nenhuma estatística nova** — `spi/alert_checks.py` só interpreta
classificações que `SpiResult`/`spi/services.py` (Etapa 7.1) já
calculam. Nenhum model novo (reaproveita `alerts.Alert`, mesmo padrão
da 7.3).

**Testado com estações sintéticas temporárias** (`joao.produtor`, 2
estações — uma "seca" com SPI-3=seca_severa/SPI-6=seca_extrema/
SPI-12=seca_extrema, outra "úmida" com SPI-3=extremamente_umido — 4
registros de `SpiResult` inseridos diretamente, já que SPI não pode
ser manipulado indiretamente via dado local igual o CHIRPS/validação
das Etapas 7.2/7.4): as 4 mensagens de alerta corretas apareceram
exatamente como esperado, idempotência confirmada (rerun: 0 novos, 4
já existentes), cartão "Alertas Climáticos" conferido no navegador via
Playwright. Rodado também contra a fazenda real do usuário (`daniel`,
id=8): **0 alertas gerados**, resultado correto — as condições atuais
(SPI-3 normal, SPI-6 muito_umido, SPI-12 normal) não caem em nenhuma
faixa de alerta. Dados de teste removidos depois (`Farm.delete()`
cascateando estação+SpiResult+Alert de teste), filtrados por owner.

**Notificações (e-mail/WhatsApp) confirmadas fora do escopo da Etapa
9**, decisão explícita do usuário — o próprio PDF já marca esse item
como "futuro", não como parte central da etapa. Mesmo tratamento já
dado à verificação de e-mail por link na Etapa 4: pendência consciente
registrada, não esquecimento.

## 2026-08-23 — Etapa 9.2: insights de texto para tomada de decisão — Etapa 9 completa

**Contexto:** segunda e última sub-etapa da Etapa 9 ("sim" do usuário
depois do resumo da 9.1). O PDF pede 7 tipos de insight (déficit
hídrico, tendência de seca, janela de plantio, risco climático,
necessidade de irrigação, tendência pluviométrica, apoio à gestão
hídrica) — "o sistema deverá **interpretar** os dados, não só
mostrar". Confirmado com o usuário via pergunta direta: texto baseado
em regras sobre SPI/chuva, **sem IA/ML**, no mesmo cartão do
dashboard (não na página da fazenda).

**Decisão central: agrupar os 7 itens do PDF em torno de só 4 sinais
de fato distintos, não escrever 7 frases separadas.** Lendo os 7 itens
com atenção, vários são a MESMA leitura climática reformulada com
palavras diferentes:
- "déficit hídrico" ≈ "necessidade de irrigação" ≈ "janela de plantio"
  desfavorável → todos são, na prática, "o SPI-3 atual está seco?".
  Uma frase só, não três.
- "tendência de seca" ≈ "tendência pluviométrica" → os dois são "o
  SPI-3 está piorando ou melhorando nos últimos meses?". Uma frase.
- "apoio à gestão hídrica" → tratado como uma leitura de médio prazo
  (SPI-6) separada da de curto prazo (SPI-3), já que gestão de
  reservatório/represa opera numa escala de tempo diferente de
  irrigação de lavoura.
- "risco climático" → resumo dos alertas já ativos (Etapa 9.1), não
  uma nova análise.

Escrever 7 frases quase-idênticas (uma "déficit hídrico: seco", outra
"necessidade de irrigação: seco", outra "janela de plantio: seco")
seria ruído, não interpretação — o PDF pede o sistema "interpretar",
que é diferente de "listar todas as palavras do requisito". Cada
função de `dashboard/insights.py` documenta explicitamente qual(is)
item(ns) do PDF ela cobre.

**Decisão: reaproveitar `spi.services.classificar_spi`, não duplicar
os limiares de classificação.** Import direto do módulo do SPI (Etapa
7.1) — a mesma lição de "não duplicar estatística" seguida em todas as
sub-etapas anteriores (7.4 correção, 8.2 comparação, 9.1 alertas).

**Decisão: "tendência" olha só os últimos 3 meses de SPI-3
disponíveis, com limiar de variação de ±0,3 pra distinguir "piora"/
"melhora" de "estável".** Limiar arbitrário (não vem do PDF nem de
literatura específica) — documentado aqui pra não parecer
cientificamente derivado; é uma escolha de UX (evitar dizer "piorando"
por causa de ruído de 0,05 no SPI).

**Nenhuma estatística nova, nenhum model novo.** `dashboard/insights.py`
só interpreta `dados_spi` (já calculado na 8.2) e `alertas_climaticos`
(já calculado na 9.1) — os dois passados de fora, sem reconsultar o
banco dentro da função de insight.

**Testado com fazenda sintética temporária** (`joao.produtor`, 3
meses de SPI-3 decrescente terminando em seca_severa + SPI-6
seca_severa + 2 alertas climáticos ativos gerados via
`detectar_alertas_climaticos`): os 4 insights esperados apareceram
juntos e corretos (déficit hídrico, tendência de piora, gestão
hídrica, risco climático — 2 alertas), conferido no navegador via
Playwright, zero erros de console. Testado também em modo leitura
contra a fazenda real do usuário (`daniel`, id=8): 2 insights corretos
(condição atual normal + tendência de piora real, do SPI-3 caindo de
1,41 pra -0,16 nos últimos 3 meses de dado real). Dados de teste
removidos depois, filtrados por owner.

**Etapa 9 (alertas e insights automáticos) está completa: 9.1 e 9.2
concluídas.**

## 2026-08-23 — Etapa 10: projeções climáticas (tendência + cenários futuros, sem ML)

**Contexto:** última etapa do roadmap original. O PDF pede "tendências
temporais, cenários futuros, análise histórica, previsão climática" —
mas marca explicitamente "machine learning; IA climática; modelos
preditivos" como **"Futuro"**, fora do escopo. Isso deixa em aberto
COMO fazer "cenário futuro"/"previsão" sem ML — decisão de
interpretação necessária antes de codar, confirmada com o usuário via
pergunta direta (opção recomendada aceita sem alteração).

**Decisão central: "cenário futuro" = climatologia histórica, não
previsão de verdade.** Em vez de tentar prever o futuro (que exigiria
modelagem — fora do escopo), o sistema descreve **o que normalmente
acontece** naquele mês do calendário, historicamente, usando os 45+
anos de CHIRPS já validados (Etapa 3.2). Três faixas por mês futuro —
"seco" (percentil 25), "normal" (mediana), "úmido" (percentil 75) —
dos totais mensais históricos do mesmo mês em todos os anos. É
estatística descritiva pura (percentis), a mesma classe de técnica já
usada em outras etapas (agregação "por mês do calendário, todos os
anos" é literalmente a mesma do SPI, Etapa 7.1). A UI deixa isso
explícito: "não é previsão de modelo climático nem machine learning".

**Decisão: tendência temporal = regressão linear simples (`ano →
total anual`).** Mesma classe de ferramenta que "correlação de
Pearson" (já usada na 7.2) — descreve se a série está subindo/descendo
ao longo do tempo, sem ser "aprendizado de máquina" (é uma fórmula
fechada, sem treinamento, sem hiperparâmetro, sem dado de validação
separado). `statistics.linear_regression`, nativo do Python 3.10+ —
sem dependência nova, mesmo módulo `statistics` já usado pra
`correlation` (7.2) e `quantiles` (10.2 — percentis).

**Decisão: tendência é calculada ON-THE-FLY; cenários são
PERSISTIDOS em `climate.Projection`.** Diferença motivada pelo próprio
model: `Projection` já existia desde a Etapa 1 com FKs
`station`/`farm`/`owner` (isolamento multiusuário, não município-level
solto) — persistir os cenários nele aproveita esse desenho já pronto e
segue o mesmo padrão "rode um comando, resultado fica salvo" já usado
em SPI/validação/alertas (Etapa 7/9). Tendência não tem um model
dedicado nem precisa — é barata de recalcular (só soma totais anuais)
e é município-level pura, sem necessidade de granularidade por
estação; calculá-la sob demanda evita persistência sem consumidor
concreto além do próprio cartão que a exibe (mesmo raciocínio já usado
pra `climate/correction.py`, Etapa 7.4).

**Migration nova:** `Projection` ganhou `unique_together = ('date',
'scenario', 'station')` (`climate.0005`) — o model original não tinha
nenhuma constraint de unicidade, e sem ela `update_or_create` não
teria como saber se uma linha (station, date, scenario) já existe.
Decisão de schema pequena, mas necessária — mesma lógica já aplicada
a `RainfallData`/`SpiResult`/`ChirpsData` em etapas anteriores.

**Redundância aceita (mesma decisão já tomada no SPI, Etapa 7.1):**
o valor do cenário é o mesmo pra todas as estações de um município
num dado (date, scenario) — grava-se 1 linha por estação mesmo assim,
em vez de mudar `Projection.station` pra opcional. Consistência com o
padrão já estabelecido, não uma decisão nova.

**Testado com dado real do usuário** (não simulado, é histórico
CHIRPS validado desde a Etapa 3.2): tendência de Tangará da Serra =
**-3,5 mm/ano** sobre 45 anos civis completos (1981-2025) — plausível
e **coerente com o resumo por década já levantado na Etapa 3.2**
(década de 2020 aparecia mais seca nas duas cidades). Normais
climatológicas: janeiro (pico da chuva) ~273mm mediana, julho (seco)
~9mm mediana — bate com a sazonalidade conhecida da região (transição
amazônica, chuvoso out-abr / seco mai-set). `gerar_projecoes` rodado
de verdade pro município ativo com estações reais (36 registros
gravados pras 2 estações do `daniel`), idempotência confirmada
(rerun: mesmos 36, sem duplicar). Cartões conferidos no navegador via
Playwright com fazenda sintética temporária (removida depois,
filtrada por owner), zero erros de console.

**Etapa 10 (projeções climáticas) está completa — a Etapa 10 era a
última do roadmap original de 10 etapas do PDF.**

## 2026-08-23 — Etapa 11: exportação de dados (fora do escopo original do PDF)

**Contexto:** com as 10 etapas do PDF fechadas, o usuário pediu uma
forma de exportar/imprimir o dado de uma fazenda pra outra plataforma
de análise. Não é um item do `docs/REQUISITOS.md` — decisão de escopo
nova, resolvida com duas perguntas diretas antes de codar (mesmo
padrão usado em toda sub-etapa desta sessão).

**Pergunta 1 — formato de exportação:** o usuário escolheu **os
dois**, Excel/CSV **e** PDF/relatório (não escolheu GeoJSON/Shapefile
— então não foi implementado exportação espacial pro dado de chuva/
SPI, só o já existente de contorno via `poligono.json`, Etapa 5).

**Decisão: um `.xlsx` com várias abas, não vários `.csv` separados.**
Um usuário abrindo os dados no Excel/R/Python prefere um arquivo só
com abas nomeadas a ter que juntar 9 arquivos `.csv` separados depois
do download. `openpyxl` já é dependência do projeto desde a Etapa 6 —
zero dependência nova. Cada aba é dado bruto (uma linha por registro),
sem nenhuma agregação/resumo — é justamente o oposto do relatório
(que É um resumo): a proposta da exportação Excel é dar munição pra
quem for **reanalisar** o dado em outra ferramenta, não repetir o que
já está na tela.

**Pergunta 2 — como gerar o PDF, já que "imprimir" foi pedido
explicitamente:** apresentei o trade-off real (biblioteca no servidor
tipo WeasyPrint vs. página formatada pra impressão + "Salvar como PDF"
do navegador) e o usuário escolheu a segunda opção.

**Decisão: SEM biblioteca de geração de PDF no servidor.**
`WeasyPrint` (opção mais comum em Django) exige bibliotecas de sistema
(Pango, Cairo, GDK-PixBuf) instaladas na imagem Docker — dependência
pesada, não-Python, com risco real de quebrar o build em ambientes
diferentes (o próprio Dockerfile já tem dependências GDAL/PostGIS
não-triviais; empilhar mais uma cadeia de libs C aumenta a superfície
de risco sem necessidade). Em vez disso: uma página HTML **standalone**
(`farms/relatorio_fazenda.html`, não estende `base.html` — sem
navbar/rodapé pra não sujar a impressão) com CSS `@media print`
(esconde o botão "Imprimir", evita quebra de página no meio de tabela).
O botão chama `window.print()`; "salvar como PDF" é o recurso nativo
de qualquer navegador moderno no diálogo de impressão — funciona sem
nenhum código adicional, em qualquer SO, sem tocar no Dockerfile.

**Refatoração: `farms/views.py` ganhou `_dados_analiticos_fazenda(fazenda)`.**
`detalhe_fazenda` já tinha ~10 queries (SPI, validação, correção,
alertas, tendência, cenários) que o relatório de impressão também
precisa mostrar (mesmo dado, layout diferente). Extraído num helper
em vez de duplicar o bloco inteiro numa segunda view — `detalhe_fazenda`
foi refatorada pra usar o helper (comportamento e template idênticos,
só reorganização interna).

**Testado com fazenda sintética temporária** (`joao.produtor`,
removida depois, filtrada por owner): as 9 abas do Excel conferidas
com conteúdo real (CHIRPS com 16.649 linhas, Fazenda/Estações/
Cenários Futuros com os valores esperados), relatório de impressão
conferido no navegador via Playwright (todas as seções presentes, dado
de tendência/cenários batendo com o já validado na Etapa 10). Também
testado em modo leitura contra a fazenda real do usuário (`daniel`,
id=8) — `gerar_workbook_fazenda`/`_dados_analiticos_fazenda` chamados
direto no shell, sem nenhuma escrita.

## 2026-08-23 — Etapa 12: manual de uso do sistema (página de Ajuda)

**Contexto:** pedido do usuário depois da Etapa 11 (exportação).
Também fora do escopo do PDF. Pergunta direta antes de codar: manual
dentro do sistema (página `/ajuda/`) vs. documento separado
(`docs/MANUAL.md`) vs. os dois. Usuário escolheu **só a página dentro
do sistema**.

**Decisão: página pública, sem `@login_required`.** As outras páginas
"internas" (painel, fazendas) exigem login porque mostram dado do
usuário. A Ajuda não mostra dado nenhum — é conteúdo estático
explicando o sistema. Deixar público ajuda quem ainda não tem conta a
decidir se vale a pena se cadastrar (a própria seção 1 já explica como
criar conta), sem forçar um cadastro só pra ler o manual.

**Decisão: `core/ajuda.html` estende `base.html`, não o template
standalone da Home.** A Home (`core/index.html`) é um documento HTML
único, sem herança de template (decisão histórica da Etapa 4 — nunca
tocar num template já testado). A Ajuda, por outro lado, é uma página
de conteúdo simples (texto + seções), sem nada que justifique reinventar
navbar/rodapé/CSS — reaproveitar `base.html` (mesmo layout usado por
`accounts`/`dashboard`) foi a escolha natural, mesmo que isso signifique
que o link de Ajuda precisou ser adicionado em DOIS lugares (a navbar
de `base.html` e a navbar própria da Home) em vez de um só.

**Decisão: 8 seções cobrindo o fluxo completo do usuário, em ordem
cronológica de uso** (criar conta → cadastrar fazenda → talhões/
estações → lançar chuva → painel → página da fazenda → exportar →
dúvidas comuns) — não em ordem alfabética nem por "importância", pra
acompanhar naturalmente a jornada de um produtor usando o sistema pela
primeira vez. Cada seção linkada por âncora no índice do topo. A
última seção ("Dúvidas comuns") antecipa as duas perguntas mais
prováveis de quem começa a usar: por que o SPI não aparece pra
algumas fazendas (limitação de município `ativo=True`, não bug) e por
que a validação CHIRPS×local fica vazia (precisa de pelo menos 3 dias
de dado local pareado).

**Nada de novo em termos de dependência ou model** — é só um `views.py`
+ template novo, mesmo padrão de qualquer página de conteúdo estático
do projeto.

**Testado no navegador via Playwright:** link "Ajuda" visível tanto
anônimo (navbar da Home) quanto logado (navbar de `base.html`),
navegação por âncora dentro da página funcionando (`#exportar` rola a
tela até a seção certa), as 8 seções presentes no HTML renderizado.

## 2026-08-23 — Etapa 13: gestão de usuários (bloquear + trocar perfil)

**Contexto:** o usuário pediu login "master"/admin (atendido promovendo
a própria conta `daniel`, com confirmação prévia entre usar a conta
demo `admin_demo` ou promover a conta real — escolheu a real). Em
seguida perguntou como bloquear um usuário, e ao mostrar print do
Painel confirmou que queria essa ação **dentro do sistema**, não só
no `/admin/` cru do Django (que já tinha a opção via o campo `is_active`
padrão do `UserAdmin`, só que "escondida" dentro da seção
"Permissões").

**Isso não é 100% fora do escopo do PDF** — `docs/REQUISITOS.md` já
pedia "permissões" dentro de "Cadastro de Usuários" (Etapa 4), com 5
perfis (administrador, pesquisador, produtor, técnico, visitante). A
Etapa 4 implementou cadastro/login/recuperação de senha e os 5 perfis
no schema (`Profile.profile_type`), mas nunca uma tela pra um admin
gerenciar OUTROS usuários — ficou pendente até agora.

**Decisão: acesso restrito a `is_superuser` OU `profile_type='admin'`,
não só um dos dois.** Contas podem ter só um dos dois setados
dependendo de como foram criadas (`seed_demo` seta os dois pro
`admin_demo`; a promoção manual desta sessão também setou os dois pro
`daniel` — mas nada garante que toda conta admin futura vai ter os
dois). Checar os dois em `_e_administrador()` evita um caso estranho
de alguém com `profile_type='admin'` mas `is_superuser=False` ficar
travado fora da tela.

**Decisão: bloquear usuário é só marcar `User.is_active=False`, o
campo nativo do Django** — não um campo novo, não um model novo. É
literalmente o mesmo mecanismo que já existia no `/admin/`, só exposto
numa tela mais direta dentro do próprio sistema. Login com conta
bloqueada falha imediatamente (Django `AuthenticationForm` já rejeita
usuário inativo por padrão) — nenhum dado do usuário é apagado.

**Decisão: proteção contra autobloqueio.** Um admin bloqueando a
própria conta se trancaria fora do sistema sem ninguém pra desbloquear
(a não ser via `/admin/` de outra conta, ou acesso direto ao banco) —
`alternar_bloqueio` recusa explicitamente `usuario == request.user`,
com mensagem de erro clara.

**Decisão: rota nova `accounts/urls_gestao.py`, separada de
`accounts/urls.py`.** `accounts/urls.py` já tem um propósito bem
definido (fluxos públicos de autenticação: login, registro,
recuperação de senha), montado em `/accounts/`. Gestão de usuários é
uma feature da ÁREA PRIVADA (só admin, precisa estar logado) — bate
com a convenção já estabelecida de `/painel/<feature>/` (fazendas,
estações, chuva), não com `/accounts/`. Por isso um arquivo de urls
separado, montado em `/painel/usuarios/` via um segundo `include()`
em `geoclima/urls.py`, mas as views continuam no app `accounts` (dono
do model `User`/`Profile`) — só a organização de URL é diferente do
padrão "1 app = 1 arquivo de urls".

**Testado com Django test client (`force_login`), sem precisar da
senha real da conta promovida a admin (`daniel`) nesta sessão** —
alternativa ao Playwright quando não se tem a senha de uma conta real:
- Bloqueio/desbloqueio de `joao.produtor` (conta de teste) confirmado
  no banco, e **confirmado de verdade que o login falha** depois de
  bloqueado (sem `_auth_user_id` na sessão do client de login) — não
  bastava só checar o campo no banco, o objetivo é a autenticação
  falhar de fato.
- Troca de perfil (`produtor` → `tecnico` → `produtor`) confirmada e
  revertida.
- `daniel` tentando bloquear a própria conta: recusado, mensagem de
  erro presente, `is_active` continuou `True`.
- Não-admin (`joao.produtor`) testado via Playwright de verdade: link
  "Gerenciar Usuários" ausente do Painel, acesso direto por URL
  redireciona pro Painel (não mostra a lista de usuários).
- Estado de `joao.produtor` restaurado ao original ao final
  (`is_active=True`, `profile_type='produtor'`); fazenda real do
  `daniel` conferida intacta.

## 2026-08-23 — Cálculo automático de SPI ao cadastrar estação nova

**Contexto:** hoje uma fazenda/estação nova num município com CHIRPS
já importado ficava sem SPI até alguém rodar `calcular_spi`
manualmente — o dashboard mostrava "Ainda não há SPI suficiente".
Pedido do usuário, com investigação exigida e aprovada antes de
qualquer código (ver `docs/HISTORICO.md` pro resultado completo da
investigação).

**Decisão: signal `post_save` em `Station`, não chamada direta nas
views.** Existem HOJE dois pontos de código que criam `Station`
(`stations/views.py:criar_estacao` e
`farms/views.py:_criar_estacoes_do_shapefile`). Colocar a chamada
direto em cada view exigiria lembrar de tocar nos dois lugares agora
e em qualquer ponto de criação futuro (ex.: uma importação em lote que
alguém adicione depois). Um signal cobre `Station.save()`
independente de quem chamou — é o único ponto de verdade "uma estação
nova entrou no sistema", igual o padrão já usado em
`accounts/signals.py` (Profile criado ao criar User).

**Decisão: assíncrono via Celery, não síncrono na view — com medição
real, não estimativa.** Rodei `calcular_spi` de verdade nesta sessão:
**~24 a 66 segundos** para recalcular um município com histórico de
45 anos, dependendo de quantas estações já existem nele (o tempo
cresce com o total de estações do município, não só a nova, porque
`calcular_spi --municipio X` recalcula todas de uma vez). Colocar isso
dentro do request-response do cadastro travaria a página por até mais
de um minuto — inaceitável, e pior ainda no cenário que motivou o
pedido (vários usuários cadastrando ao mesmo tempo numa demonstração,
todos competindo pelo mesmo worker Django síncrono). `celery_worker`
já é serviço obrigatório do `docker-compose.yml` desde a Etapa 3.3 —
não é infraestrutura nova, só mais uma task nele.

**Trade-off registrado explicitamente (era requisito do pedido):**

| | Síncrono | Assíncrono (escolhido) |
|---|---|---|
| Cadastro do usuário | Trava 24-66s | Responde na hora (medido: 719ms via Playwright) |
| SPI/Insight disponível | Imediato, mesma página | Alguns segundos/minuto depois — usuário pode precisar recarregar o dashboard |
| Risco sob carga | Alto (timeout de request em cenário de demo com vários usuários) | Nenhum pro cadastro em si |
| Infra | Nenhuma nova | Nenhuma nova (`celery_worker` já obrigatório) |

**Decisão: task nova (`spi/tasks.py:calcular_spi_municipio`) só chama
o management command via `call_command`, não reimplementa nada.**
Mesmo padrão já usado por `climate/tasks.py:atualizar_chirps` com
`import_chirps` — a task decide QUANDO disparar, o command continua
sendo o único lugar com a lógica de cálculo/gravação. Recalcula pra
TODAS as estações do município (não só a nova) — inofensivo, é
`update_or_create` idempotente, e é exatamente o que `calcular_spi
--municipio X` já faz manualmente hoje.

**Decisão: `municipio.ativo` como critério de disparo, não uma
checagem nova.** É o mesmo sinal já usado em todo o projeto pra "este
município tem CHIRPS suficiente" (SPI, validação, correção, tendência,
cenários todos usam esse critério) — inventar um segundo critério
(ex.: checar `calcular_serie_spi` primeiro) duplicaria uma decisão que
já existe. Se `ativo=True` mas o histórico ainda for curto demais pra
alguma escala, a própria `calcular_serie_spi` já lida com isso (devolve
`[]`), sem erro — mesmo comportamento de rodar o comando manualmente.

**Nenhuma migration** — nem o signal nem a task tocam em nenhum model.

**Testado com dado real de execução (não simulado):**
- Estação criada (via `Station.objects.create()`, simulando o caminho
  do Shapefile): task recebida pelo worker (log confirmado), SPI
  calculado em produção real (~66s pra 4 estações no município nesse
  momento), `dashboard.services.serie_spi()` e
  `dashboard.insights.gerar_insights()` passaram a devolver dado
  correto pra fazenda de teste sem nenhum `calcular_spi` manual.
- Estação criada num município `ativo=False` (Acrelândia/AC): zero
  task disparada (log do worker conferido vazio), zero erro, cadastro
  seguiu normal — confirma o requisito "não fazer nada" literalmente,
  não só por inspeção de código.
- Cadastro via formulário real no navegador (Playwright,
  `/painel/estacoes/nova/`): resposta HTTP em **719ms**, mensagem de
  sucesso na tela — confirma que o cálculo de ~1 minuto roda
  inteiramente em background, sem travar o usuário.
- Dados de teste removidos depois, filtrados por
  `owner=joao.produtor`; as duas fazendas reais do `daniel`
  ("fazenda Rocha" e "faz Taruma") conferidas intactas antes e depois.

## 2026-08-23 — Pipeline climático completo automático: Celery chain + guarda de debounce

**Contexto:** extensão do disparo automático de `calcular_spi` (entrada
anterior) pra incluir também `gerar_projecoes` e
`detectar_alertas_climaticos`, respeitando a ordem obrigatória (o
detector de alertas lê o SPI mais recente — rodar antes do SPI
atualizado dá alerta desatualizado ou vazio).

**Decisão: Celery `chain` (Opção B), não uma task única com 3
`call_command` em sequência (Opção A) — escolha do usuário, entre as
duas opções que eu levantei.** `chain` é o primitivo do próprio Celery
pra exatamente esse requisito ("etapa 2 só roda se etapa 1 terminou"),
com retry independente por etapa — se `gerar_projecoes` falhar, só ele
re-tenta, não recalcula o SPI (24-66s) de novo à toa. Uma task
monolítica funcionaria (todos os 3 commands são idempotentes, um
retry do zero não corrompe nada), mas perderia essa granularidade e
fugiria do padrão já estabelecido no projeto: uma task = um command
(`atualizar_chirps` → `import_chirps`, `calcular_spi_municipio` →
`calcular_spi`). Cada task nova mora no app dono do command que ela
chama: `gerar_projecoes_task` em `climate/tasks.py` (command do app
`climate`), `detectar_alertas_climaticos_task` em `spi/tasks.py`
(command do app `spi`, ao lado de `calcular_spi_municipio`).

**Achado real, não hipotético, que motivou uma decisão nova nesta
tarefa:** nem `gerar_projecoes` nem `detectar_alertas_climaticos`
aceitam `--municipio` — os dois rodam sempre globais (todos os
municípios `ativo=True`, ou a base de `SpiResult` inteira,
respectivamente). Hoje isso é barato porque só existem 2 municípios
ativos; se o projeto ativar mais no futuro, esse custo cresce sem
controle a cada estação nova cadastrada em QUALQUER município — não é
um problema resolvido aqui (mudar isso exigiria alterar os
management commands, fora do escopo pedido), só registrado como
limitação conhecida caso o projeto cresça pra mais municípios.

**Decisão: guarda de debounce via `django.core.cache.cache.add()`,
TTL de 120s, chave por `codigo_ibge`.** Sem isso, o caminho do
Shapefile (`farms/views.py:_criar_estacoes_do_shapefile`, que cria
várias `Station` numa única requisição) dispararia uma chain completa
e redundante — até ~77s cada — por PONTO do arquivo, todas
recalculando o mesmo SPI/cenários/alertas do mesmo município ao mesmo
tempo. `cache.add()` é atômico (grava só se a chave ainda não existe),
evitando corrida entre requisições concorrentes — mais seguro que um
`.get()` seguido de `.set()` separados. TTL de 120s escolhido com
folga sobre o tempo medido do pipeline completo (~77s no pior caso),
não é um valor científico, é uma margem de segurança.

**Limitação conhecida e documentada da guarda: `LocMemCache` é por
processo, não compartilhado.** O projeto não configura `CACHES` em
`geoclima/settings.py` — o padrão do Django é `LocMemCache`, que vive
na memória de UM processo Python só. Isso funciona corretamente para
o caso real (toda estação cadastrada por um usuário passa pela mesma
única instância do serviço `web`/`runserver` — confirmado testando
duas estações via navegador em sequência, 1 único disparo). **Não
funcionaria** se o projeto um dia escalar `web` para múltiplos
processos/réplicas (cada um teria seu próprio `LocMemCache`, sem
saber do lock do outro) — nesse momento, trocar para um backend de
cache compartilhado (Redis, que o projeto já usa pro Celery) antes de
confiar nesta guarda de novo. Descoberto durante o próprio teste desta
tarefa: testar via `manage.py shell` em chamadas separadas (cada uma
um processo Python distinto) mostrou a guarda "falhando" — não é bug,
é o mesmo limite: cada chamada de shell tem seu próprio
`LocMemCache`, isolado do processo `web` real e um do outro.

**Testado com execução real (não simulada):** ver
`docs/HISTORICO.md` pro relatório completo — chain de 3 etapas
executando na ordem certa (medido: 47s + 0,8s + 1,3s), debounce
confirmado bloqueando 1 de 2 disparos no cenário real (navegador,
mesmo processo), cadastro respondendo em 539ms via Playwright, dado
real do usuário intacto antes/depois.

**Pendência registrada, não implementada aqui (pedido explícito do
usuário pra só registrar):** o dashboard hoje não distingue "município
sem CHIRPS" de "SPI sendo calculado agora" — as duas situações mostram
a mesma mensagem ambígua. Ver `docs/HISTORICO.md` pro detalhe da
solução possível (reaproveitar a chave de debounce, ou `AsyncResult`),
fica pra uma tarefa futura com esse escopo.

## 2026-08-23 — Cache do Django trocado pra Redis (fecha a limitação da entrada anterior)

**Contexto:** o usuário perguntou, antes de subir a entrada anterior
pro GitHub, onde `CACHES` apontava — confirmado (`grep` em
`geoclima/settings.py`, sem nenhuma ocorrência) que era o padrão do
Django, `LocMemCache`. O usuário informou um dado que eu não tinha:
**a produção real roda 3 workers do Gunicorn**, não o `runserver`
único que o `docker-compose.yml` deste repositório usa em
desenvolvimento — exatamente o cenário "múltiplos processos" que a
entrada anterior já apontava como o limite de quando `LocMemCache`
para de funcionar. Com 3 processos independentes, cada um teria seu
próprio `LocMemCache` isolado — a guarda de debounce (`cache.add()`
em `stations/signals.py`) não protegeria nada entre eles: até 3
estações cadastradas quase ao mesmo tempo (uma por worker) passariam
cada uma pelo seu `cache.add()` sem saber das outras, disparando até 3
pipelines completos e redundantes.

**Decisão: backend Redis nativo do Django
(`django.core.cache.backends.redis.RedisCache`), não `django-redis`
nem nenhuma lib nova.** Disponível desde o Django 4.0 (este projeto
usa 4.2) — usa o pacote `redis` que já é dependência do projeto desde
sempre (pro broker/backend do Celery). Zero linha nova em
`requirements.txt`.

**Decisão: banco Redis separado do usado pelo Celery — `db 1`, não
`db 0`.** `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` já usam
`redis://redis:6379/0`. Em vez de reaproveitar o mesmo banco pro cache
do Django, criei uma variável nova (`CACHE_REDIS_URL`, padrão
`redis://redis:6379/1` no `docker-compose.yml`, só no serviço `web` —
é o único que cria `Station` e roda a guarda; `celery_worker`/
`celery_beat` não precisam). Não é estritamente necessário (as chaves
de cada um têm formato bem diferente, risco de colisão é baixo), mas
separa dado operacional do broker/result-backend do Celery de dado de
cache de aplicação — mais fácil de raciocinar sobre os dois
separadamente (ex.: um `FLUSHDB` de manutenção num não afeta o outro).

**Container precisou ser recriado, não só reiniciado** — variável de
ambiente nova no `docker-compose.yml` só é aplicada com `docker
compose up -d web` (recria o container com a env atualizada);
`docker compose restart web` mantém as variáveis com que o container
foi criado originalmente. Detalhe operacional que vale lembrar pra
qualquer variável de ambiente nova adicionada daqui pra frente.

**Testado com prova direta, não só confiança na configuração:**
- Backend confirmado via `type(caches['default'])` →
  `django.core.cache.backends.redis.RedisCache`.
- Chave gravada por `cache.set()` conferida **fisicamente** dentro do
  Redis via `redis-cli -n 1 KEYS` — não só que o Django não reclamou.
- **O teste decisivo**: `cache.add()` da mesma chave rodado em duas
  chamadas `manage.py shell` **genuinamente separadas** (dois
  processos Python distintos, o mesmo tipo de isolamento que existe
  entre workers do Gunicorn) — processo A grava (`True`), processo B
  vê o lock do processo A e é bloqueado (`False`). Esse era
  exatamente o teste que "falhava" na entrada anterior com
  `LocMemCache`; agora passa.
- Pipeline completo (cadastro real via navegador → chain de 3 etapas)
  re-testado do zero com o backend novo: resposta em 613ms, as 3
  etapas rodando em ordem e com sucesso, dado real do usuário
  conferido intacto antes/depois.
