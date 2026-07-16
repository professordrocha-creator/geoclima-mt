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

Antes de implementar uma feature nova, confira `docs/ROADMAP.md` para
saber se a etapa correspondente já tem alguma base pronta.
