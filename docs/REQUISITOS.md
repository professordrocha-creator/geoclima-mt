# Requisitos — GeoClima MT

> Transcrição fiel do documento original **"PROMPT MASTER COMPLETO — GeoClima MT
> (Geotecnologia e Clima para Mato Grosso)"** (PDF fornecido pelo usuário).
> Nenhum item foi adicionado, removido ou reinterpretado — este arquivo é a
> fonte da verdade dos requisitos. O estado real de implementação de cada
> item está em [ROADMAP.md](ROADMAP.md) e [ARQUITETURA.md](ARQUITETURA.md).

## Sistema Climático Inteligente para Mato Grosso

Quero desenvolver um sistema climático online chamado **ACTS (AgroClima
Tangará da Serra)**, baseado em pesquisa científica sobre precipitação,
secas e validação do CHIRPS para o estado de Mato Grosso.

> Nota: o repositório real do projeto foi nomeado **GeoClima MT**; "ACTS" é o
> nome usado no documento de requisitos original.

O sistema será desenvolvido usando:

- Django
- PostgreSQL
- PostGIS
- Docker
- Django REST Framework
- Leaflet
- OpenStreetMap
- CHIRPS
- Google Earth Engine
- Celery
- Redis
- Nginx

O objetivo do sistema é criar uma plataforma climática inteligente para:

- monitoramento de precipitação;
- cálculo de secas;
- análise climática;
- integração de dados locais;
- apoio à tomada de decisão agrícola;
- gestão hídrica;
- projeção de cenários climáticos.

O sistema será dividido em:

- área pública;
- área privada multiusuário.

---

## Área Pública (sem login)

O index principal será público e acessível para qualquer pessoa.

**Objetivo:**

- servir como portal climático de Mato Grosso;
- apresentar informações climáticas em tempo real;
- divulgar dados públicos;
- permitir acesso rápido ao clima regional.

### Funcionalidades públicas

**Mapa Climático de Mato Grosso**

- mapa interativo;
- municípios de MT;
- zoom;
- seleção de cidades;
- camadas climáticas.

**Clima Atual** — Mostrar:

- temperatura;
- precipitação;
- umidade;
- vento;
- sensação térmica;
- condição climática atual.

**Previsão do Tempo** — Mostrar:

- previsão para 7 dias;
- probabilidade de chuva;
- acumulado previsto;
- tendência climática.

**Mapas Meteorológicos** — Mostrar:

- nuvens em tempo real;
- radar meteorológico;
- precipitação acumulada;
- imagens climáticas.

**Dados Públicos CHIRPS** — Mostrar:

- precipitação histórica;
- anomalias;
- gráficos climáticos;
- séries temporais.

**Interface Pública** — A página inicial deve possuir:

- dashboard climático;
- visual moderno;
- gráficos;
- mapas;
- informações em tempo real;
- responsividade para celular.

---

## Área Privada (com login)

Após login, o sistema entra nas funcionalidades científicas e privadas.
Cada usuário poderá acessar **SOMENTE** seus próprios dados.

Nenhum usuário poderá visualizar:

- fazendas;
- sensores;
- pluviômetros;
- estações;
- análises;
- dashboards;
- SPI;
- relatórios;
- dados históricos de outros usuários.

O sistema deve funcionar como plataforma multiusuário segura.

### Funcionalidades privadas

**Cadastro de Usuários** — Criar:

- login;
- registro;
- recuperação de senha;
- permissões;
- perfil do usuário.

Perfis:

- administrador;
- pesquisador;
- produtor;
- técnico;
- visitante.

**Cadastro de Fazendas** — Cada usuário poderá:

- cadastrar fazendas;
- cadastrar talhões;
- cadastrar coordenadas geográficas;
- visualizar fazendas no mapa.

Campos:

- nome;
- município;
- latitude;
- longitude;
- área;
- cultura agrícola;
- observações.

**Cadastro de Estações Meteorológicas** — Cada fazenda poderá possuir:

- estações automáticas;
- pluviômetros manuais;
- sensores.

Tipos:

- Davis;
- Ecowitt;
- Ambient Weather;
- IoT;
- manual;
- CSV importado.

---

## Dados Climáticos

O sistema trabalhará com múltiplas fontes:

### 1. CHIRPS

Fonte principal regional.

Funções:

- precipitação histórica;
- precipitação diária;
- séries temporais;
- comparação climática.

Características:

- resolução ~5 km;
- histórico desde 1981;
- atualização contínua.

### 2. Dados Manuais

Usuário poderá lançar:

- chuva diária;
- horário;
- observações;
- anotações de campo.

Objetivo:

- permitir uso por pequenos produtores;
- permitir uso com pluviômetro convencional.

### 3. Dados de Estações da Fazenda

Usuário poderá:

- importar CSV;
- importar Excel;
- conectar APIs futuras;
- integrar sensores automáticos.

---

## Tipos de Origem dos Dados

Criar campo: `source_type`

Valores:

- `CHIRPS`
- `MANUAL`
- `STATION`
- `IMPORTED_CSV`
- `API`

---

## Validação dos Dados

O sistema deverá:

- comparar CHIRPS com dados locais;
- calcular erros;
- calcular viés;
- gerar métricas estatísticas.

Métricas:

- R²
- RMSE
- MAE
- MBE
- índice d
- índice c

---

## Detecção de Inconsistências

O sistema deverá detectar:

- chuva negativa;
- valores extremos;
- dados duplicados;
- falhas temporais;
- inconsistências.

Gerar alertas automáticos: **"Possível inconsistência detectada."**

---

## Correção Local

O sistema deverá permitir:

- calibração regional;
- correção de viés;
- ajuste local do CHIRPS.

Exemplo:

- CHIRPS estimou 100 mm;
- estação local registrou 112 mm;
- sistema aprende diferença regional.

---

## SPI — Índice de Precipitação Padronizada

Implementar: SPI-3; SPI-6; SPI-12.

Usar:

```
SPI = (Xi - X̄) / σ
```

Classificações:

- extremamente úmido;
- muito úmido;
- normal;
- seca moderada;
- seca severa;
- seca extrema.

---

## Dashboard Privado

Cada usuário terá dashboard individual. Mostrar:

- chuva atual;
- acumulados;
- SPI;
- tendências;
- gráficos;
- mapas;
- comparação CHIRPS × local;
- previsão climática.

---

## Sistema de Alertas

Criar:

- alerta de seca;
- alerta de excesso de chuva;
- risco hídrico;
- anomalias climáticas.

Futuro:

- email;
- WhatsApp;
- notificações.

---

## Insights para Tomada de Decisão

O sistema não deverá apenas mostrar dados. O sistema deverá **interpretar**
os dados.

Gerar insights automáticos como:

- risco de déficit hídrico;
- tendência de seca;
- janela favorável de plantio;
- risco climático;
- necessidade de irrigação;
- tendência pluviométrica;
- apoio à gestão hídrica.

---

## Projeções Climáticas

Criar:

- tendências temporais;
- cenários futuros;
- análise histórica;
- previsão climática.

Futuro:

- machine learning;
- IA climática;
- modelos preditivos.

---

## Sistema Geoespacial

Implementar:

- mapas interativos;
- Leaflet;
- OpenStreetMap;
- geolocalização;
- camadas climáticas;
- visualização espacial.

---

## Google Earth Engine

Integrar:

- CHIRPS;
- processamento climático;
- mapas;
- imagens;
- séries temporais.

---

## Arquitetura do Backend

Criar apps:

- `core`
- `accounts`
- `farms`
- `stations`
- `climate`
- `spi`
- `alerts`
- `dashboard`
- `maps`
- `api`

---

## Infraestrutura

Usar:

- Docker
- Docker Compose
- Nginx
- Redis
- Celery

Funções:

- processamento automático;
- tarefas agendadas;
- atualização diária;
- download automático dos dados climáticos.

---

## Banco de Dados

Usar: PostgreSQL; PostGIS

Criar tabelas:

- `users`
- `farms`
- `stations`
- `rainfall_data`
- `chirps_data`
- `spi_results`
- `alerts`
- `projections`

Todos os dados devem possuir:

- `owner_id`
- `farm_id`
- `station_id`

Garantindo:

- isolamento de usuários;
- segurança;
- privacidade.

---

## Segurança

Implementar:

- autenticação;
- autorização;
- isolamento multiusuário;
- permissões;
- proteção de dados.

Nenhum usuário poderá acessar dados de outro usuário.

---

## Etapas de Desenvolvimento

- **Etapa 1** — Estrutura base: Docker; Django; PostgreSQL; PostGIS.
- **Etapa 2** — Sistema geoespacial: mapas; municípios; Leaflet.
- **Etapa 3** — Integração CHIRPS: download; importação; armazenamento.
- **Etapa 4** — Login e usuários.
- **Etapa 5** — Fazendas e estações.
- **Etapa 6** — Importação CSV e dados manuais.
- **Etapa 7** — Cálculo SPI.
- **Etapa 8** — Dashboards e gráficos.
- **Etapa 9** — Alertas e insights automáticos.
- **Etapa 10** — Projeções climáticas.

---

## Objetivo Final

Criar uma plataforma climática inteligente para Mato Grosso capaz de:

- monitorar precipitação;
- calcular secas;
- integrar dados locais;
- validar dados climáticos;
- gerar insights;
- apoiar produtores;
- apoiar gestão hídrica;
- apoiar pesquisa científica;
- apoiar tomada de decisão agrícola.

Todo código do sistema deve ser comentado.

O sistema deverá ter um manual do usuário.
