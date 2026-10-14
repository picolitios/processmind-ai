# ProcessMind AI: instruções do repositório

- Leia `specs/implementation-plan.md` e a spec da funcionalidade antes de editar código.
- `specs/` é a fonte de verdade para requisitos; divergências exigem registro e correção antes de alterar comportamento.
- Implemente uma fase por vez. A Fase 1 cria apenas a fundação, sem endpoints de negócio fictícios.
- Backend modular por domínio em `apps/api/app/features`; dependências compartilhadas apenas em `app/core` e `app/db`.
- Toda consulta a dados empresariais deve receber `organization_id` validado a partir da sessão e filtrar por ele; índices e FKs compostas reforçam o isolamento.
- Não use `create_all` em runtime; use migrações Alembic versionadas.
- Não registre arquivos importados, credenciais, tokens nem conteúdo integral de prompts em logs.
- Teste, execute lint e verificação de tipos pertinentes antes de declarar uma fase concluída.
- Não implemente itens pós-MVP antes da Fase 8.
