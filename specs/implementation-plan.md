# Plano, backlog e dependências

## Plano curto

Objetivo: entregar primeiro a especificação coerente e depois uma fundação executável. Fase 0 altera `specs/`, `AGENTS.md` e `README.md`; Fase 1 cria `apps/api`, `apps/web`, `infra`, `compose.yaml`, migrações e CI. Validações: revisão cruzada, parse OpenAPI, execução local, testes, lint, tipos e build quando houver código.

## Backlog priorizado

| ID | Fase | Entrega | Depende de | Aceite / evidência |
| --- | --- | --- | --- | --- |
| B00 | 0 | Visão, requisitos, arquitetura, dados, OpenAPI, segurança, testes, ADRs | — | Documentos completos e coerentes; nenhum endpoint fictício em runtime |
| B01 | 1 | Monorepo e configurações | B00 | Instalação local documentada, TS strict e Python tipado |
| B02 | 1 | FastAPI, PostgreSQL, Alembic, health e Compose | B01 | Migração inicial aplica; readiness consulta banco; serviço sobe |
| B03 | 1 | React/Vite e CI de lint, tipos, testes e build | B01 | UI inicial honesta e pipeline verde |
| B04 | 2 | Cadastro, sessão, CSRF, organizações, RBAC | B02 | M01–M03; isolamento testado em dois tenants |
| B05 | 3 | Upload, prévia, mapeamento, normalização e histórico | B04 | M04–M05; original rastreável e erros por linha |
| B06 | 3 | Gerador sintético e gabarito | B05 | M13; semente reproduz 4 tamanhos |
| B07 | 4 | Jobs, regras determinísticas, estatística e achados | B05–B06 | M06–M07; avaliação de gabarito publicada |
| B08 | 5 | Ollama, schemas, explicações e fallback | B07 | M08; evidência validada e auditoria independente |
| B09 | 6 | UI completa, dashboard e analytics | B04–B08 | M10, M12; dados reais, filtros e estados |
| B10 | 6 | Casos, comentários e trilha | B04, B07 | M09, M11; decisões rastreáveis e E2E completo |
| B11 | 7 | Segurança, carga, acessibilidade, revisão | B09–B10 | Gates da estratégia de testes aprovados |
| B12 | 8 | Instalação limpa, guia, exemplo, screenshots e resumo | B11 | Terceiro técnico executa e avalia sem ajuda |

`B03` e `B02` podem avançar em paralelo após `B01`. `B10` não depende de Ollama. O fluxo E2E exige `B09` e `B10`. Dependências pós-MVP ficam em `mvp.md`, sem tickets de implementação antecipada.

## Plano de execução da Fase 4

1. Corrigir o gabarito sintético e a validação de ID de compra repetido, alinhando a entrada à regra DUPLICATE.
2. Versionar as nove regras e seus limites; criar `AuditRun`, catálogo de regras, achados e evidências com FKs por organização.
3. Expor criação idempotente e consultas paginadas; executar auditoria no worker persistido, com snapshot da configuração.
4. Testar regras, isolamento, idempotência e gabarito; validar migração, lint, tipos, testes e Compose. Nenhuma interface de casos ou IA entra nesta fase.

## Estado

- Fase 0: concluída após revisão de contrato, cobertura de requisitos, dependências e limites de escopo.
- Fase 1: concluída após Compose com PostgreSQL saudável, migração `0001_foundation`, liveness/readiness, web HTTP 200, testes, lint, tipos, build e auditoria npm. A CI correspondente está configurada; sua execução remota depende de um repositório Git remoto.
- Fase 2: concluída na API com cadastro, login, sessão, logout, CSRF, organizações, membros, RBAC, throttle e testes de dois tenants. A interface dessas operações pertence à Fase 6. Testes locais com PostgreSQL e fluxo HTTP via Compose passaram; CI remota segue pendente de remoto Git.
- Fase 3: concluída na API com CSV/XLSX, prévia, mapeamento, limite de upload, hash/reimportação explícita, job persistido, linhas normalizadas com erros, compras por tenant e gerador sintético reproduzível nos quatro tamanhos. Testes PostgreSQL de fluxo e corpus adversarial passaram. A interface visual pertence à Fase 6; as regras de auditoria começam na Fase 4.
- Fase 4: concluída na API e no worker com nove regras v1.0.0, estatística conservadora, execuções idempotentes, catálogo versionado, achados e evidências por tenant. Gabarito sintético corrigido e avaliado em 100/1k/10k/50k linhas; teste PostgreSQL cobre criação, isolamento, RBAC e consulta. Revisão humana e casos pertencem à Fase 6.
