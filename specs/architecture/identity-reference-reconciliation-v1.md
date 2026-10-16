# Reconciliação de referências à identidade v1

Este incremento mede a integridade das referências de negócios antes de qualquer alteração de FK. Não modifica dados, contratos HTTP, constraints nem credenciais.

## Inventário obrigatório

- Toda tabela de negócios com `organization_id` deve apontar para uma organização existente, inclusive `audit_configurations` e `business_audit_events`, que não possuem FK com identidade.
- `import_batches.uploader_id`, `audit_runs.requester_id`, `ai_analyses.requester_id` e `business_audit_events.actor_user_id` (opcional) devem apontar para usuários existentes.
- `audit_cases.assignee_membership_id` (opcional) e `case_comments.author_membership_id` devem apontar para membros da **mesma organização**. A inativação de usuário, organização ou membro não invalida referência histórica.
- O inventário de tabelas deve detectar novas tabelas com `organization_id` não classificadas. Uma falha de esquema ou consulta não pode ser relatada como resultado limpo.

## Contrato do comando

- Executar em transação PostgreSQL `REPEATABLE READ READ ONLY` para produzir um retrato consistente.
- Emitir JSON com contagens por relação: registros verificados, IDs ausentes e referências de membro com tenant divergente. Não emitir e-mail, dados importados ou UUIDs individuais.
- Retornar código `0` quando todas as verificações passaram, `2` para inconsistência de dados ou inventário, `1` para falha técnica. Uma conexão indisponível deve falhar fechada.
- Permitir execução local e no contêiner da API com a configuração `DATABASE_URL` existente. O comando não é endpoint público nem job periódico.

## Aceite

1. Todos os tipos de referência acima são cobertos e a lista de tabelas corresponde ao schema atual.
2. Teste com referência órfã em tabela sem FK faz o comando indicar falha, sem persistir o registro de teste.
3. Banco íntegro retorna código `0`; banco ou schema indisponível retorna falha técnica.
4. O relatório do Compose local é registrado na documentação sem concluir que as FKs podem ser removidas. Antes da remoção ainda são necessários política de exclusão, contratos e plano de rollback.
