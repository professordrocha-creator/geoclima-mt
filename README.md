# GeoClima MT

Este é o repositório para o projeto GeoClima MT, um sistema de inteligência geográfica e monitoramento climático focado na região de Mato Grosso.

## Implementações Recentes na Home (19/06/2026)

Hoje implementamos as seguintes melhorias e funcionalidades na página inicial (Home):

*   **Visual Premium com Cards Dinâmicos:** A interface da Home foi atualizada com um design mais moderno e premium, utilizando cards dinâmicos para exibir informações climáticas de forma clara e interativa.
*   **Badges para UV/AQI:** Adicionamos badges visuais para o Índice UV (Ultravioleta) e o AQI (Índice de Qualidade do Ar), permitindo uma rápida visualização e compreensão dos níveis.
*   **Esteira de 4 Mapas Agrícolas:** Foi incorporada uma esteira com quatro cards dedicados a mapas agrícolas do Brasil (Satélite, Previsão de Queimadas, Chuva Acumulada - CHIRPS e Temperatura), oferecendo acesso rápido a informações relevantes para o setor.
*   **Ajuste de Proporção do Mapa Leaflet:** O mapa interativo do Leaflet foi ajustado para ter uma proporção e visualização otimizadas na Home, garantindo uma melhor experiência do usuário.
*   **Rodapé Institucional:** Um rodapé com informações institucionais foi adicionado, contendo detalhes sobre o projeto GeoClima MT e a origem dos dados.
*   **Painel de Monitoramento do Windy:** Integramos um painel de monitoramento meteorológico em tempo real utilizando um iframe do Windy.com, que exibe dados de satélite e radar para a região.

## Usuários de desenvolvimento (`seed_demo`)

> ⚠️ **SOMENTE DESENVOLVIMENTO.** Estas credenciais são públicas (estão
> neste arquivo) e o comando que as cria se recusa a rodar se
> `DEBUG=False`. Nunca usar em produção/beta público.

Para criar os usuários de teste da Etapa 4 (login/perfis):

```bash
docker compose exec web python manage.py seed_demo
```

| Usuário | Senha | Perfil | Observação |
|---|---|---|---|
| `admin_demo` | `AdminDemo#2026` | admin (+ superusuário Django) | acesso a `/admin/` e a todos os papéis |
| `joao.produtor` | `Produtor#2026` | produtor | "João da Silva", sem fazenda cadastrada ainda (Etapa 5) |

O comando é idempotente: rodar de novo não recria nem reseta a senha de
quem já existe.