# Corte das FKs de referências à identidade v1

Status: incremento reversível da Fase 2 da evolução arquitetural. Depende de
`identity-reference-reconciliation-v1.md`, `membership-boundary-v1.md`,
`case-membership-lookup-v1.md` e `organization-authorization-boundary-v1.md`.

## Política de identidade e dados históricos

- Organizações, usuários e associações são desativados, nunca apagados fisicamente
  neste incremento. Não existe endpoint público de exclusão. Triggers temporários
  de banco rejeitam DELETE e TRUNCATE nessas três tabelas durante a transição, inclusive para
  identidades sem dados empresariais. Uma política legal futura deverá substituir
  este bloqueio por um fluxo explícito antes de permitir exclusão física.
- UUIDs históricos de tenant, ator e membro permanecem nos registros empresariais.
  A inativação não reescreve autoria, responsabilidade ou tenant. Consultas de
  histórico usam o contrato privado de referências, que admite membros inativos.
- Toda escrita pública de negócios exige sessão e associação ativa no tenant;
  referências de membros são validadas no serviço de identidade para o mesmo
  tenant. Workers derivam tenant e ator de registros previamente autorizados.
  FKs compostas entre tabelas de negócios continuam protegendo o isolamento.

## Migração

- Após reconciliação limpa e testes de autorização, remover apenas as 11 FKs
  de tabelas de negócios para `organizations`, `users` e
  `organization_memberships`: `import_batches` (2), `jobs` (1), `suppliers` (1),
  `audit_runs` (2), `ai_analyses` (2), `audit_cases` (1),
  `case_comments` (1) e `outbox_events` (1).
- Preservar colunas, nulabilidade, índices, unicidades e FKs entre tabelas de
  negócios. A migração é transacional, não modifica linhas e cria o bloqueio de
  DELETE antes de soltar as constraints.
- O downgrade recria as 11 FKs, com validação integral pelo PostgreSQL, e só
  então remove o trigger. Se surgir órfão, o downgrade falha sem abandonar o
  bloqueio de exclusão nem aceitar uma restauração incompleta. Primeiro corrigir
  o dado após investigação, sem apagamento automático.

## Operação e aceite

1. Executar a reconciliação antes e depois do upgrade; `missing=0`,
   `wrong_tenant=0` e inventário sem erro são gates. Falha técnica impede corte.
2. Em banco descartável, testar upgrade, isolamento entre dois tenants,
   revogação, alteração de papel, caso com membro inativo, snapshot concorrente,
   downgrade e novo upgrade. API, E2E, lint, tipos e build permanecem verdes.
3. DELETE e TRUNCATE diretos das três tabelas de identidade falham após o upgrade.
   Dados históricos e resposta pública permanecem iguais.
4. A migração não isola credenciais por si só. Compatibilidade com o antigo modo
   de banco e FKs entre domínios continua disponível via downgrade validado.

## Fora do escopo

Mover tabelas entre schemas, criar roles de runtime, remover rotas de identidade
da API de negócios e revogar acesso a tabelas privadas exigem outro incremento.
