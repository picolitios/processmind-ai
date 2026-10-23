# Interface v1 — Fase 6

## Navegação e dados

- React Router organiza as onze telas obrigatórias por organização. As rotas ficam em `apps/web/src/features`, separadas por domínio, e são carregadas sob demanda. A área autenticada mostra a organização ativa e seu papel; a seleção troca o prefixo da rota.
- Cada tela da organização oferece um botão de retorno à tela anterior da navegação interna. Em acesso direto ou após recarga, o retorno tem destino previsível: detalhe → lista da seção, seção → visão geral, visão geral → organizações. O botão não deve navegar para uma origem externa.
- O cliente usa `/api/v1` no mesmo domínio, cookie HttpOnly e `csrf_token` da sessão em mutações. Após criar organização, a sessão é atualizada para incorporar o novo vínculo. Dados empresariais são requisitados sempre com o ID da organização da rota; o backend valida associação e papel em cada operação.
- TanStack Query guarda consultas por organização e filtros, refaz consultas de jobs em andamento e invalida listas após mutações. Coleções longas oferecem paginação por cursor. Estados de carregamento, erro e vazio são explícitos; mensagens de erro vêm do contrato da API, sem expor detalhes internos.

## Permissões e decisões

- Viewer consulta. Owner/Admin/Analyst podem importar, auditar, revisar, abrir e modificar casos e solicitar IA; Owner/Admin editam parâmetros, e apenas Owner gerencia membros. O backend permanece a autoridade final de autorização.
- A importação exige prévia e mapeamento dos campos obrigatórios. Só importações concluídas entram em auditorias. O achado mostra justificativa e evidências antes das ações de revisão ou abertura de caso.
- O detalhe de `DUPLICATE` compara lado a lado as duas compras, identifica os campos iguais, informa se vieram da mesma importação e deixa explícito que a duplicidade real depende de conferência humana. A comparação determinística permanece disponível sem IA.
- IA é opcional e apresentada como apoio. O painel mostra a limitação devolvida pelo backend em falhas e não altera estado de auditoria ou caso. O dashboard usa apenas indicadores persistidos; rankings são de compras auditadas e a ausência de categoria é declarada.
- Um caso por achado durante todo o histórico; encerramento pede justificativa. Comentários e eventos permanecem consultáveis após encerramento. O formulário só oferece transições válidas para o estado atual.

## Verificação

- O E2E Playwright em `apps/web/e2e/phase6.spec.ts` percorre cadastro, organização, CSV, mapeamento, auditoria, achado DUPLICATE, caso, atribuição, comentário, resolução e indicador. Usa a aplicação via Compose com API, PostgreSQL e worker reais.
- Gates da Fase 6: build/typecheck, lint, Vitest, Ruff, Mypy, Pytest com PostgreSQL isolado e E2E. A Fase 7 acrescenta auditoria de acessibilidade, carga e segurança.
