# Plano, backlog e dependências

## Plano curto

Evolução arquitetural pós-MVP: `specs/architecture/audit-events-v1.md` define o primeiro fluxo executável. A sequência, limites e rollback estão em `docs/architecture/migration-plan.md`. As Fases 0–8 abaixo são o histórico do MVP; não representam os estágios da evolução distribuída.
Os primeiros recortes da Fase 2 estão em `specs/architecture/identity-boundary-v1.md`, `specs/architecture/membership-boundary-v1.md` e `specs/architecture/case-membership-lookup-v1.md`: processo e roteamento de identidade separados, sessão/CSRF, autorização de associação e referências de membros em casos via contratos privados. O estado atual do Compose já separa schemas e credenciais de runtime, conforme `specs/architecture/identity-schema-credential-boundary-v1.md`; as descrições dos incrementos abaixo registram seu escopo histórico.

A primeira entrega funcional da V2 é o copiloto conversacional definido em `specs/architecture/copilot-v2.md`. Backend, contrato, interface, guia e E2E dos modos normal e temporário compõem a mesma entrega; o modelo local precisa estar disponível para gerar respostas em vez da limitação explícita.

`specs/architecture/import-dedup-lock-v1.md` removeu o bloqueio de deduplicação de importações da linha de organização sem alterar a semântica de concorrência. O snapshot de configuração da auditoria e as FKs entre domínios foram migrados nos incrementos posteriores descritos abaixo.

`specs/architecture/audit-configuration-ownership-v1.md` define o primeiro incremento da migração do snapshot: tabela própria, backfill e leitura controlada com rollback. A gravação cruzada transitória e as FKs ainda impedem a declaração de isolamento de credenciais.

`specs/architecture/audit-configuration-coordination-v1.md` define o corte da gravação direta da identidade, com comando durável, aplicação privada idempotente, reconciliação e resposta pública síncrona após confirmação.

`specs/architecture/organization-authorization-boundary-v1.md` define a retirada da releitura e do bloqueio de `organizations` pela API de negócios em modo de identidade, com snapshot serializado na configuração própria e modo local de rollback.

`specs/architecture/business-audit-trail-v1.md` define o incremento seguinte: histórico de negócios em tabela própria, backfill de eventos legados e escrita atômica transitória nas duas tabelas. O histórico público de caso continua igual.

`specs/architecture/business-audit-trail-cutover-v1.md` define a retirada controlada da escrita legada, com reconciliação somente de leitura e restauração idempotente para rollback durante a janela de banco compartilhado.

`specs/architecture/identity-reference-reconciliation-v1.md` define a verificação somente de leitura das referências de tenant, ator e membro antes de qualquer remoção de FK. O resultado local e os bloqueios restantes constam em `docs/architecture/reference-reconciliation-2026-10-16.md`.

`specs/architecture/identity-reference-fk-cutover-v1.md` define o corte reversível das FKs entre negócios e identidade, com bloqueio temporário de exclusão física, validação de referências e downgrade integral. `specs/architecture/identity-schema-credential-boundary-v1.md` define o incremento posterior, já aplicado no Compose, que move tabelas para schemas próprios e limita os papéis de runtime.

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
- Fase 5: concluída na API e no worker com análises opcionais via Ollama, schema estrito, citação validada de evidências, limites de contexto, circuito de falhas e fallback explícito. Testes cobrem resposta válida, referência inventada, injeção em dados, indisponibilidade, idempotência, RBAC e isolamento; a auditoria segue independente da IA. A interface visual pertence à Fase 6.
- Fase 6: concluída. API de revisão, casos, comentários paginados e indicadores validada com PostgreSQL; onze telas pt-BR conectadas à API, com sessão/CSRF, RBAC, estados de carregamento/erro/vazio, mapeamento, auditoria, explicação opcional, decisões e comentários. Fluxo E2E cadastro → organização → importação → auditoria → achado → caso → atribuição → comentário → resolução → indicador passou em Compose. Lint, tipos, build, Vitest e 17 testes Python passaram; os testes Python foram repetidos em banco novo para evitar jobs obsoletos de execuções anteriores.
- Fase 7: estabilização concluída em branch própria. Headers, cache, acessibilidade, ingestão de 50 mil linhas, concorrência e auditoria de dependências validados. Resultados e limites em `specs/testing/phase7-results.md` e `specs/testing/phase7-load-report.md`; CI remota e revisão do PR seguem o fluxo de integração.
- Fase 8: instalação isolada com novos volumes, migração e E2E completos; guias, CSV de exemplo, capturas, OpenAPI e backlog futuro disponíveis. O relatório de aceite consta em `specs/testing/phase8-delivery.md`. PRs empilhados aguardam revisão e integração.
- Versão 2, copiloto conversacional: política e aprovação por organização, chats normais/temporários, memória delimitada por tenant, citações verificadas e worker implementados. Painéis de achado/auditoria, configurações, guia e E2E dos dois modos foram acrescentados no PR da entrega. A disponibilidade efetiva de respostas depende do Ollama configurado; o fallback foi validado sem alterar auditorias ou casos.
- Evolução distribuída, operação da auditoria: `specs/architecture/audit-operations-v1.md` define o diagnóstico agregado e somente de leitura da outbox, filas RabbitMQ e jobs de auditoria, com limiares opcionais. A retenção v1 preserva eventos publicados e dead letters até existir política de expurgo comprovada por volume e restauração.

## Plano de execução da Fase 6

1. Definir transições de revisão e casos; persistir casos, comentários e trilha com isolamento por organização e migração Alembic.
2. Entregar consultas agregadas do dashboard com filtros de período e dados reais, mantendo o contrato OpenAPI sincronizado.
3. Construir as onze telas pt-BR sobre a API existente, incluindo CSRF, RBAC, navegação, estados vazio/erro/carregamento, responsividade e teclado.
4. Validar fluxos de API e E2E cadastro → importação → auditoria → achado → caso → resolução; executar lint, tipos, testes, build, migrações e Compose.
