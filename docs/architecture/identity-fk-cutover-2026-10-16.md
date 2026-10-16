# Verificação local do corte de FKs — 2026-10-16

Ambiente: banco PostgreSQL de teste `processmind_org_boundary_final_1610`,
separado do banco principal do Compose. O schema inicial estava em
`9b6d2f41a8c3` e continha dados dos testes de API.

- Antes do corte, o banco principal do Compose passou na reconciliação das 20
  relações: zero IDs ausentes, zero membros de outro tenant, inventário limpo.
- No banco de teste, `upgrade head` aplicou `6fd3a81b29c4`; a suíte Python
  executou 41 testes com sucesso, incluindo isolamento, autorização, snapshot
  concorrente, preservação das FKs internas e bloqueio de DELETE físico.
- `downgrade 9b6d2f41a8c3` recriou 11 FKs e retirou os triggers. Catálogo:
  11 FKs entre negócios e identidade, zero guards.
- Novo `upgrade head` resultou em zero FKs entre negócios e identidade e seis
  triggers (DELETE e TRUNCATE nas três tabelas de identidade). O ciclo completo
  de downgrade e upgrade foi repetido sobre essa versão final; terminou no mesmo
  catálogo. Os dois testes de schema e bloqueio físico passaram novamente.
- A reconciliação após o primeiro upgrade encontrou zero IDs ausentes, zero
  membros de outro tenant e inventário sem erros. Lint, mypy e validação de
  specs passaram. A suíte completa final teve 41 testes aprovados. Esta
  verificação local não demonstra isolamento de credenciais;
  schemas, roles e retirada das rotas de compatibilidade continuam pendentes.

O banco principal do Compose não recebeu a migração deste incremento durante
esta verificação. Qualquer aplicação existente deve repetir reconciliação,
upgrade e reconciliação antes de alterar credenciais ou permissões.
