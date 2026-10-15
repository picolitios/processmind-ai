# ProcessMind AI — resumo técnico

Plataforma SaaS B2B de auditoria operacional de compras. O MVP recebe CSV/XLSX, normaliza registros com erros por linha, executa nove regras determinísticas versionadas e organiza achados em casos com responsável, comentários, decisão e trilha. A IA local via Ollama é opcional e explica evidências sem decidir a auditoria.

## Arquitetura

React/Vite no web; FastAPI na API; PostgreSQL com migrações Alembic; worker persistido para importação, auditoria e análise opcional; Docker Compose para execução local. Consultas e relacionamentos de dados empresariais são isolados por organização, com RBAC, sessão HttpOnly, CSRF, paginação e idempotência em operações relevantes. O [desenho do sistema](../specs/architecture/system-design.md), o [modelo de dados](../specs/architecture/data-model.md) e o [OpenAPI](../specs/architecture/openapi.yaml) detalham as decisões.

## Evidências

- Fluxo E2E cadastro → organização → importação → auditoria → achado → caso → resolução → painel aprovado em instalação Compose com volumes novos.
- Fase 7: 18 testes Python, 3 E2E Playwright, lint, tipos, build, validador de specs e CI remota aprovados. O [relatório](../specs/testing/phase7-results.md) registra limites e avisos.
- Carga sintética reproduzível de 100, 1.000, 10.000 e 50.000 compras. No host de desenvolvimento, a ingestão de 50.000 linhas caiu de 323,919 s para 29,207 s com processamento em lotes; esses números não são um SLO de produção.

## Demonstração

O [guia de uso](user-guide.md) permite reproduzir o cenário com um CSV pequeno sem Ollama. O [guia de instalação](installation.md) prepara o ambiente e as [capturas](user-guide.md#capturas-da-demonstração) mostram caso e painel. Código e decisões são versionados; o [backlog futuro](future-backlog.md) mantém recursos posteriores fora da entrega atual.
