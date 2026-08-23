# CLAUDE.md — GeoClima MT

## O que é este projeto

GeoClima MT é uma plataforma climática para Mato Grosso: monitoramento de
precipitação, cálculo de secas (SPI), validação/calibração do CHIRPS,
gestão hídrica e apoio à decisão agrícola. Tem uma área pública (sem
login, portal climático) e uma área privada multiusuário (cada usuário só
acessa seus próprios dados — fazendas, estações, análises, alertas).

Os requisitos completos do sistema (fonte da verdade, não editar sem pedido
explícito) estão em [docs/REQUISITOS.md](docs/REQUISITOS.md).

## Documentação do projeto

- [docs/REQUISITOS.md](docs/REQUISITOS.md) — requisitos originais completos
  (transcrição fiel do PDF fornecido).
- [docs/ARQUITETURA.md](docs/ARQUITETURA.md) — o que existe de fato hoje no
  código (apps, models, infraestrutura). Atualizar sempre que a arquitetura
  mudar de verdade.
- [docs/ROADMAP.md](docs/ROADMAP.md) — checklist das Etapas 1–10, com o que
  já está pronto e o que falta. Atualizar o checklist ao concluir itens.
- [docs/HISTORICO.md](docs/HISTORICO.md) — changelog de desenvolvimento.
  Adicionar uma entrada nova a cada sessão de trabalho relevante.
- [docs/DECISOES.md](docs/DECISOES.md) — decisões de arquitetura e o
  porquê delas (ex.: por que a plataforma é genérica para qualquer
  município do Brasil e não só para a região da pesquisa). Adicionar uma
  entrada quando uma decisão não-óbvia for tomada.

Antes de assumir que algo existe ("já tem SPI calculado", "já tem login"),
confira `docs/ARQUITETURA.md` — vários models do projeto foram desenhados
mas ainda não têm migração aplicada nem lógica de negócio implementada.

## Stack (fixa — não trocar sem pedido explícito do usuário)

- Django (+ Django REST Framework)
- PostgreSQL + PostGIS (`django.contrib.gis`)
- Docker / Docker Compose
- Celery + Redis
- Leaflet + OpenStreetMap (mapas)
- CHIRPS (fonte de precipitação regional) + Google Earth Engine
- Nginx (produção — ainda não presente no `docker-compose.yml` atual)

## Estrutura de apps Django

`core`, `accounts`, `farms`, `stations`, `climate`, `spi`, `alerts`,
`dashboard`, `maps`, `api` — um app por domínio, conforme definido nos
requisitos. Não criar apps novos fora dessa lista sem necessidade clara.

## Convenções de código observadas no repositório

- Todo arquivo `.py` começa com um comentário indicando o caminho relativo
  (ex.: `# accounts/models.py`). Manter esse padrão.
- **Todo código deve ser comentado** — é um requisito explícito do PDF do
  projeto, não apenas uma preferência de estilo.
- `verbose_name` dos campos de model em português (ex.:
  `verbose_name="Nome da Fazenda"`).
- Isolamento multiusuário: toda tabela de dado (chuva, SPI, alertas,
  projeções, estações) tem FKs `owner` (User), `farm` (Farm) e, quando
  aplicável, `station` (Station), todas com `on_delete=models.CASCADE`.
  Manter esse padrão em qualquer model novo que armazene dado de usuário.
- Models geoespaciais usam `django.contrib.gis.db.models` e um campo
  `geom = models.PointField(srid=4326, ...)` além dos floats
  `latitude`/`longitude` (os dois convivem — não remover um em favor do
  outro sem confirmar com o usuário).
- `choices` de model em inglês minúsculo/snake_case como valor
  (`'seca_moderada'`, `'excess_rain'`) com rótulo em português como label.

## Estado atual (resumo — ver docs/ROADMAP.md para detalhe)

Etapa 1 (Docker/Django/PostGIS) concluída. Todos os apps com model já têm
migração aplicada no banco (desde 2026-07-16). A maior parte ainda tem só
o *model* escrito, sem admin, views, forms ou lógica de negócio. As
funcionalidades ponta-a-ponta hoje são: a Home pública (`core`), que busca
clima da Open-Meteo direto do navegador; o seletor de município da
Etapa 2.2 (`maps.Municipio` + endpoints em `api/`), que desenha o contorno
do município escolhido no Leaflet e recarrega o clima no centroide; e a
integração CHIRPS/Google Earth Engine, **Etapa 3 completa**
(`climate/management/commands/import_chirps.py`), que grava a média
zonal diária de precipitação por município `ativo=True` em
`climate.ChirpsData` — autenticação via conta de serviço (projeto GCP
`climatga`, chave em `secrets/gee-key.json`, não versionada). O backfill
histórico completo (1981-01-01 a 2026-06-30, 33.234 registros, 0
buracos, 0 negativos) já foi rodado e validado, e desde 2026-07-16 a
série se mantém em dia sozinha via `climate/tasks.py`
(`atualizar_chirps`), agendada às 04:00 `America/Cuiaba` num serviço
`celery_beat` dedicado (separado do `celery_worker` — ver
[docs/DECISOES.md](docs/DECISOES.md)). Ver DECISOES.md também sobre por
que a plataforma é genérica para qualquer município do Brasil, não só os
da pesquisa (Tangará da Serra/Cáceres), e sobre a escolha de GEE + média
zonal para o CHIRPS.

**Etapa 4 (login e usuários) também está completa** (2026-07-16):
autenticação própria em `/accounts/` (login, logout, registro,
recuperação de senha por e-mail — nativo do Django, sem libs de
terceiros), `Profile` criado automaticamente via signal com papel padrão
`produtor`, admin com `Profile` embutido no `User`, e `/painel/`
(app `dashboard`) como placeholder protegido por login — a Etapa 8 vai
estender essa mesma view, não criar uma nova. Usuários de teste via
`python manage.py seed_demo` (`admin_demo`/`joao.produtor`, credenciais
no README, comando recusa rodar em produção). Verificação de e-mail por
link **não** foi implementada — pendência consciente até antes de um
beta público, ver DECISOES.md.

**Etapa 5 (fazendas e estações) também está completa** (2026-08-23):
CRUD completo de fazenda/talhão (`farms/`) e estação (`stations/`) em
`/painel/fazendas/` e `/painel/estacoes/`, tudo `@login_required` e
isolado por `owner=request.user` (testado no navegador com dois
usuários — acesso direto por URL a dado de outro usuário dá 404).
`Farm.municipio` agora é FK para `maps.Municipio` (reaproveita o mesmo
seletor Estado→Cidade da Home), não texto livre. Model novo `Talhao`.
Os três formulários usam um mapa Leaflet "clique para marcar" em vez de
o usuário digitar coordenadas — e o cadastro de fazenda também aceita
importar um Shapefile (`.zip`, `farms/shapefile_import.py`): polígono
vira `Farm.poligono` (novo campo `MultiPolygonField`), pontos viram
`Station` automaticamente. Três armadilhas documentadas em DECISOES.md
que vale ler antes de mexer nesses templates/dados de novo: (1)
`{{ valor_float }}` embutido direto num `<script>` quebra por causa da
localização pt-br (vírgula em vez de ponto) — sempre envolver com
`{% load l10n %}{% localize off %}`; (2) `on_delete=CASCADE` do Django
cascateia em Python (`.delete()` do ORM), não é uma constraint do
Postgres — nunca apagar essas tabelas direto via SQL; (3) **nunca rodar
`.delete()`/`DELETE` sem filtro explícito por `owner`** — um
`Farm.objects.all().delete()` sem filtro já apagou dado real do
usuário nesta sessão (sem backup configurado, perda definitiva).

**Etapa 6 (importação CSV/Excel e lançamento manual) também está
completa** (2026-08-23): `climate/` ganhou seus primeiros
forms/views/urls/admin (`/painel/chuva/`) — lançamento manual de chuva
e importação de arquivo (`.csv`/`.xlsx`, lib nova `openpyxl`,
decisão explícita do usuário) com um parser único
(`climate/data_import.py`) que detecta colunas pelo nome do cabeçalho.
Gravação sempre por `update_or_create(station, date, source_type)` —
idempotente. `RainfallData` ganhou `time`/`notes` (faltavam, o PDF
pedia). Mais uma armadilha de formulário documentada em DECISOES.md:
`<input type="date">`/`type="time"` também quebram com
`LANGUAGE_CODE=pt-br` se o widget não tiver `format="%Y-%m-%d"`/
`"%H:%M"` explícito — o campo fica vazio ao editar (mesma família do
bug de `{% localize off %}`, mas em widget de form, não em `<script>`).
E o autoreload do `runserver` travou de novo ao criar uma pasta de
templates nova (2ª vez que acontece) — se um app ganhar
`templates/` pela primeira vez, mais vale já reiniciar o container
proativamente em vez de descobrir com um 500.

**Etapa 7 (SPI) está em andamento, quebrada em sub-etapas** (mesmo
padrão da integração CHIRPS): **7.1 (cálculo do SPI) já está completa**
(2026-08-23) — `spi/services.py` calcula SPI-3/6/12 a partir do CHIRPS
(única fonte com histórico longo o bastante; `RainfallData` do usuário
ainda é recente demais), `spi/management/commands/calcular_spi.py`
grava por estação via `update_or_create`. **Só funciona hoje pra
municípios `ativo=True`** (Tangará da Serra/Cáceres) — mas isso é
limite de DADO, não de código (nenhum município é citado por nome em
`spi/`); qualquer município novo com `ativo=True` + backfill de CHIRPS
passa a ter SPI automaticamente. Cartão "SPI atual" aparece no detalhe
da fazenda. **7.2 (validação estatística CHIRPS × local) também
completa** (2026-08-23, mesmo dia): model novo
`climate.ChirpsValidation` (1 resultado por estação, sempre o mais
recente — não histórico), `climate/validation.py` calcula R²/RMSE/
MAE/MBE/índice d (Willmott)/índice c (Camargo-Sentelhas — padrão
agrometeorológico brasileiro, `c = r × d`), comando `validar_chirps`.
Mesma restrição de dado do SPI (só municípios `ativo=True`). Testado
com cenário sintético matematicamente controlado (transformação linear
conhecida) pra confirmar as fórmulas, não só que "rodou sem erro".
Cartão "Validação CHIRPS × Dado Local" também no detalhe da fazenda.
**7.3 (detecção de inconsistências) também completa** (2026-08-23,
mesmo dia): reaproveita `alerts.Alert` (schema-only desde a Etapa 1,
sem lógica de geração até aqui) em vez de criar model novo — novo
`alert_type='inconsistency'`. `climate/quality_checks.py` roda 4
checagens sobre `RainfallData` local (chuva negativa, valor extremo
>200mm, valor repetido 3+ dias, gap de 5+ dias sem lançamento),
`climate/management/commands/detectar_inconsistencias.py` grava um
`Alert` por achado (`get_or_create`, idempotente). Formulário de
lançamento manual também bloqueia chuva negativa na entrada
(`LancamentoManualForm.clean_value`). Cartão "Possíveis Inconsistências
no Dado Local" no detalhe da fazenda, só aparece se houver alerta
ativo. 3º caso (não mais surpreendente, ver DECISOES.md) do bug de
autoreload travado do `runserver` — desta vez ao editar um arquivo já
existente (`farms/views.py`), não ao criar arquivo/pasta nova; resolvido
com `docker compose restart web` como sempre. **7.4 (correção/calibração
local do CHIRPS) também completa** (2026-08-23, mesmo dia) — **Etapa 7
inteira concluída**: `climate/correction.py` corrige o CHIRPS bruto
subtraindo o MBE já calculado pela `ChirpsValidation` da 7.2 (sem
estatística nova, sem model nem command novos, tudo calculado
on-the-fly a cada carregamento da página). Cartão "CHIRPS Corrigido
(Calibração Local)" no detalhe da fazenda, últimos 10 dias bruto ×
corrigido, só aparece pra estação já validada. Testado com viés
constante sintético conhecido (+10mm): correção reproduziu o valor
local exatamente. A correção **não** realimenta o SPI (nível
município vs. nível estação — ver DECISOES.md).

**Etapa 8 (dashboards e gráficos) está em andamento, quebrada em
sub-etapas** (mesmo padrão da CHIRPS/SPI): **8.1 (estrutura do
dashboard + chuva atual/acumulados + gráfico de série) já está
completa** (2026-08-23) — `dashboard/services.py` (novo:
`chuva_atual`/`acumulados`/`serie_chuva`, tudo on-the-fly sobre
`RainfallData`/`ChirpsData`, sem model novo) agrega **por fazenda**
(não por usuário nem por estação — um usuário pode ter fazendas em
municípios diferentes). `dashboard/views.py` (`painel`) estendida
com seletor de fazenda (`?fazenda=<id>`), mesma rota da Etapa 4, não
uma nova. Dado local e CHIRPS nunca somados no mesmo número — local
tem prioridade, CHIRPS só entra como fallback quando não há
lançamento local numa janela. Primeiro uso de **Chart.js via CDN**
no projeto (gráfico de linha "Série de Chuva", sem dependência
Python nova). Testado com a fazenda real do usuário só em modo
leitura (sem `.save()`/`.delete()`) e com fazenda sintética temporária
para os cenários de escrita — gráfico conferido com pixels de fato
desenhados no canvas via Playwright, não só "sem erro de JS".
**8.2 (tendência do SPI + comparação CHIRPS×local em gráfico) também
completa** (2026-08-23, mesmo dia): `serie_spi(farm)` devolve **uma
linha por data com SPI-3/6/12 como colunas** (não uma lista por
escala) — SPI-12 só começa depois de 12 meses de janela móvel, então
alinhar por índice de array em vez de por data desalinharia o
gráfico; achado e corrigido pensando no design, não por erro visto
depois. `comparacao_chirps_local(farm)` reaproveita
`climate.validation.pares_chirps_local`, sem estatística nova.
Gráfico de dispersão CHIRPS×local com linha diagonal de referência.
Testado igual à 8.1 (fazenda sintética pros cenários de escrita,
fazenda real só leitura). **8.3 (mapa geral + previsão climática)
também completa** (2026-08-23, mesmo dia) — **Etapa 8 inteira
concluída**: só `dashboard/painel.html` mudou, sem tocar `views.py`/
`services.py` (nenhum dos dois itens precisou de agregação nova).
Mapa Leaflet mostra **todas** as fazendas do usuário de uma vez (não
só a selecionada no dropdown, que é o escopo dos outros cartões).
Previsão climática é fetch **client-side direto pra Open-Meteo**,
mesmo padrão já usado pela Home pública desde sempre — sem proxy
Django novo. Mapeamento de `weather_code` duplicado (reduzido) do de
`core/index.html`, mesmo espírito do comentário original ali ("por
segurança", sem bundler no projeto). Testado com 2 fazendas
sintéticas em municípios diferentes (2 marcadores confirmados,
`fitBounds` correto) e uma chamada real (não mockada) à Open-Meteo.

**Etapa 9 (alertas e insights automáticos) está completa** (9.1 +
9.2, notificações email/WhatsApp confirmadas fora do escopo — é
"futuro" no PDF, decisão explícita do usuário): **9.1 (alertas de
seca/excesso de chuva/risco hídrico/anomalia)** — `spi/alert_checks.py`
(novo): 4 funções olhando o `SpiResult` **mais recente** de cada
estação (condição atual, não histórico), cada uma numa escala do SPI
diferente pra não duplicar sinal — seca e excesso de chuva usam SPI-3
(lados opostos da mesma distribuição), risco hídrico usa SPI-6 (mais
severo, médio prazo), anomalia usa SPI-12 (só extremos, longo prazo).
Command `spi/management/commands/detectar_alertas_climaticos.py`
grava via `alerts.Alert` (`get_or_create`, idempotente, mesmo padrão
da 7.3). Cartão "Alertas Climáticos" em `farms/detalhe_fazenda.html`,
separado do cartão de inconsistência da 7.3 (tipos diferentes:
qualidade do dado vs. condição climática real). **9.2 (insights de
texto para tomada de decisão)** (2026-08-23, mesmo dia): `dashboard/
insights.py` (novo) agrupa os 7 tipos de insight do PDF em 4 sinais
distintos (vários são a mesma leitura reformulada — déficit
hídrico/irrigação/janela de plantio viram um insight só, do SPI-3
atual; tendência de seca/pluviométrica viram outro, da variação do
SPI-3 em 3 meses; gestão hídrica usa SPI-6; risco climático resume os
alertas da 9.1), sem IA/ML (decisão confirmada com o usuário),
reaproveitando `spi.services.classificar_spi` sem duplicar limiares.
Cartão "Insights" em `dashboard/painel.html`. Ambas testadas com dado
sintético cobrindo todos os casos e contra a fazenda real do usuário
em modo leitura.

**Etapa 10 (projeções climáticas) também está completa** (2026-08-23,
mesmo dia) — **encerra o roadmap original de 10 etapas do PDF**.
Confirmado com o usuário antes de codar (pergunta direta): sem machine
learning/IA/modelos preditivos (explicitamente "futuro" no PDF).
`climate/trends.py` (novo): `tendencia_anual(municipio)` (regressão
linear simples sobre totais anuais, `statistics.linear_regression`
nativo, sem dependência nova, calculada on-the-fly) e
`cenarios_futuros(municipio)` (3 faixas seco/normal/úmido = percentis
25/50/75 do histórico do mesmo mês do calendário — "o que normalmente
chove", não previsão de modelo). `Projection` (model do PDF, sem uso
desde a Etapa 1) ganhou `unique_together` (`climate.0005`) e passou a
ser gravado de verdade via `climate/management/commands/gerar_projecoes.py`.
Cartões "Tendência Histórica" e "Cenários Futuros" em
`farms/detalhe_fazenda.html`. Testado com dado real: -3,5 mm/ano de
tendência em Tangará da Serra sobre 45 anos, coerente com o resumo
por década já levantado na Etapa 3.2. **Todas as tabelas do projeto
têm lógica de verdade agora — nenhuma continua "schema sem uso".**

**Etapa 11 (exportação de dados) também completa** (2026-08-23, mesmo
dia) — **fora do escopo original das 10 etapas do PDF**, pedido do
usuário depois de fechar o roadmap. Duas perguntas diretas antes de
codar: formato (usuário escolheu Excel/CSV **e** PDF/relatório, não
GeoJSON) e abordagem do PDF (usuário escolheu página pra imprimir via
navegador, **não** biblioteca no servidor — evita dependência pesada
tipo WeasyPrint, que exigiria libs de sistema Pango/Cairo no
Dockerfile). `farms/exports.py` (novo): `.xlsx` com 9 abas (Fazenda,
Estações, Talhões, Chuva Local, CHIRPS do Município, SPI, Validação
CHIRPS, Alertas, Cenários Futuros) via `openpyxl` (já dependência
desde a Etapa 6, sem lib nova). `farms/relatorio_fazenda.html` (novo):
página standalone (sem navbar/rodapé), CSS `@media print`, botão
"Imprimir/Salvar como PDF" via `window.print()` — o "PDF" é o recurso
nativo do navegador, não gerado no servidor. `farms/views.py` ganhou
o helper `_dados_analiticos_fazenda(fazenda)` (refatorado de
`detalhe_fazenda`, reaproveitado pelo relatório). Botões "Relatório" e
"Exportar Excel" em `farms/detalhe_fazenda.html`. Testado com fazenda
sintética (9 abas populadas, CHIRPS com 16.649 linhas) e contra a
fazenda real do usuário em modo leitura.

**Etapa 12 (manual de uso do sistema) também completa** (2026-08-23,
mesmo dia) — pedido do usuário depois de um susto de UX (não achava
os botões novos da Etapa 11 — era página errada, não bug). Pergunta
direta confirmou: página de Ajuda **dentro** do sistema, não documento
separado. `core/views.py:ajuda` (view pública, sem login) +
`core/templates/core/ajuda.html` (novo) — 8 seções em ordem
cronológica de uso (conta, fazenda, talhões/estações, chuva, painel,
página da fazenda, exportação, dúvidas comuns), com índice de âncoras.
Rota `GET /ajuda/`. Linkado em dois lugares (navbar de `base.html` +
navbar própria da Home, que não usa `base.html`). Testado no navegador
via Playwright.

**Etapa 13 (gestão de usuários) também completa** (2026-08-23, mesmo
dia) — pedido do usuário logo depois de virar administrador da própria
conta (promovido `is_superuser`/`is_staff`/`profile_type='admin'`, a
pedido dele, escolhendo a conta real em vez da demo `admin_demo`).
Bloquear/desbloquear já existia no `/admin/` (campo `is_active` do
`UserAdmin`), mas o usuário queria dentro do próprio sistema — mais
trocar o perfil (papel) do usuário, confirmado por pergunta direta.
`accounts/views_gestao.py` (novo): `lista_usuarios`,
`alternar_bloqueio` (`User.is_active`, recusa autobloqueio),
`alterar_perfil` (`Profile.profile_type`). Acesso restrito a
`is_superuser` ou `profile_type='admin'`. Rota `/painel/usuarios/`
(`accounts/urls_gestao.py`, namespace `gestao_usuarios`, separado de
`accounts/urls.py` que só tem fluxos públicos de auth). Link
"Gerenciar Usuários" no Painel, só visível pra admin. Isso completa
parte do que a Etapa 4 do PDF original deixava em aberto ("permissões"
dentro de "Cadastro de Usuários", nunca implementado). Testado com
Django test client (sem precisar da senha real do `daniel`): bloqueio
faz o login falhar de verdade (sessão não criada, não só campo no
banco), autobloqueio recusado, troca de perfil confirmada e revertida;
e com Playwright de verdade confirmando que não-admin não vê o link
nem acessa a URL direto.

Antes de implementar uma feature nova, confira `docs/ROADMAP.md` para
saber se a etapa correspondente já tem alguma base pronta.
