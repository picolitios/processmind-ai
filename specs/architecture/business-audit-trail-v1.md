# Trilha de eventos de negócios v1

O corte posterior da gravação dupla está definido em `business-audit-trail-cutover-v1.md`.

As ações de importação, auditoria, IA, revisão de achados e casos pertencem ao domínio de negócios. A identidade conserva os eventos de usuário, sessão, organização e membros. A resposta de histórico do caso mantém o contrato atual.

## Incremento de migração

- Criar `business_audit_events`, append-only, com UUID, organização, ator opcional, ação, assunto, metadados mínimos, correlação e horário. Não criar FK para tabelas privadas da identidade.
- Copiar os registros antigos com prefixos de ação `import.`, `audit.`, `ai.`, `finding.` e `case.`, preservando IDs e horários. Não apagar a tabela legada.
- Após o backfill, gravar cada evento de negócio nas duas tabelas na mesma transação, com o mesmo ID, horário e conteúdo. Esta gravação cruzada é transitória para rollback do código e não concede isolamento de credenciais.
- Consultar `business_audit_events` no histórico de caso. Manter limite, ordenação, filtro por organização e formato da resposta.
- Parar API, identidade e workers que gravem esses eventos antes da migração; verificar contagens e cópia antes de reiniciar. Falha na segunda gravação deve abortar a operação inteira.

## Aceite

1. Backfill de eventos legados preserva o histórico de caso e os IDs, sem duplicar linhas ao reaplicar uma migration concluída.
2. Criação e atualização de casos, auditorias, importações e análises registram eventos em ambas as tabelas atomicamente.
3. A consulta de histórico de caso exibe eventos antes e depois da migração, restritos ao tenant.
4. Código anterior pode voltar a ler a tabela legada; nenhuma tabela ou evento é removido.
