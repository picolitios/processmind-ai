# Validação do conector GitHub público v1

Data: 29/10/2026. Fonte externa de teste autorizada:
`picolitios/processmind-ai/README.md` (repositório público).

## Gates executados

- API real de conteúdo do GitHub respondeu com o arquivo UTF-8 (10.413
  caracteres) e SHA do blob. A chamada usou somente `api.github.com`, sem token.
- Alembic `upgrade head → downgrade -1 → upgrade head` passou em banco
  PostgreSQL descartável novo. O banco de testes antigo estava marcado na
  revisão anterior, mas sem a coluna `knowledge_revisions`; por isso a suíte
  completa foi executada no banco novo, sem reparar nem descartar aquele banco.
- Pytest no banco novo: 106 passaram, 1 ignorado. Os testes do conector cobrem
  validação de caminho, host fixo, limite de tamanho, texto inválido,
  redireção, CSRF, isolamento de tenant, papel viewer, duplicidade, refresh,
  falha externa e revogação.
- Ruff, Mypy, typecheck, build, Vitest e validação OpenAPI passaram. ESLint
  terminou sem erros, com cinco avisos preexistentes de Fast Refresh.
- Antes do upgrade da demo, o backup quiescido de PostgreSQL e uploads foi
  criado e verificado. A migração e o provisionamento de papéis passaram; o
  gate `verify_deployment.py` retornou `status: ok` para os 11 serviços.
- E2E na URL HTTPS pública temporária com Ollama `gemma3:4b`: o administrador
  importou o README real, habilitou o agente, recebeu resposta com citação
  documental e abriu a página interna da cópia, com origem e SHA visíveis.
- Após atualizar a API da demo para o último commit, o gate dos 11 serviços
  voltou a `status: ok`. Na URL pública, os cenários GitHub, agente flutuante
  e fluxo completo de compras passaram com Ollama real. O primeiro ciclo
  encontrou apenas um seletor ambíguo no teste do agente (`Título` versus
  `Título para o agente`); após torná-lo exato, esse cenário passou novamente.

## Limites

O conector usa uma cópia verificada; atualização é manual e a página distingue
a cópia da versão atual do GitHub. A API pública sem autenticação tem limite
compartilhado por IP. Não há acesso a repositórios privados, credenciais ou
sincronização contínua. A demo Quick Tunnel depende do computador ligado e
seu endereço muda a cada início.
