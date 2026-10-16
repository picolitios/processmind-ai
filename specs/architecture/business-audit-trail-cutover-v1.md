# Corte da gravação legada de eventos de negócio v1

Este incremento sucede `business-audit-trail-v1.md`. A trilha `business_audit_events`
já recebeu backfill, é a fonte do histórico de casos e conserva o evento na mesma
transação da operação de negócio. A exigência de gravação dupla da v1 vale para o
incremento de preparação; este documento define sua retirada controlada.

## Comportamento

- `BUSINESS_EVENT_WRITE_MODE=dual` grava o mesmo evento, ID e horário nas duas
  tabelas, na mesma transação. É o padrão do processo sem Compose e a opção de
  retorno durante a janela de migração.
- `BUSINESS_EVENT_WRITE_MODE=owned` grava apenas em `business_audit_events`.
  Compose seleciona esse modo em API, worker de importação e consumidor de
  auditoria. A identidade continua gravando seus próprios eventos em `audit_events`.
- A API pública, o histórico dos casos, o isolamento por organização e a
  atomicidade do evento de negócio permanecem iguais.
- Valores desconhecidos de configuração impedem o início do processo.

## Reconciliação e rollback

`python -m app.db.reconcile_business_events` é somente leitura e informa contagens
de eventos exclusivos de cada tabela e de registros com o mesmo ID mas conteúdo
divergente. Eventos de identidade não entram na contagem de exclusivos da tabela
legada. Antes de ativar `owned`, `legacy_only` e `conflicts` devem ser zero; no
período anterior de escrita dupla, `owned_only` também deve ser zero.

Para voltar a uma imagem que só lê/grava `audit_events`, interromper API e todos
os workers que emitem eventos; executar
`python -m app.db.reconcile_business_events --restore-legacy` com a credencial de
migração atual; exigir `owned_only=legacy_only=conflicts=0`; só então reiniciar a
imagem anterior. A restauração adiciona por ID apenas linhas ausentes, sem alterar
ou remover eventos existentes, e pode ser repetida. Conteúdo divergente ou evento
legado sem cópia exige investigação, nunca correção automática. O comando ainda
precisa acessar as duas tabelas no banco compartilhado; antes da separação de
credenciais, o procedimento de rollback deve ser reavaliado.

## Aceite

1. Em `owned`, uma ação de negócio cria evento próprio e nenhuma cópia legada.
2. Em `dual`, as duas linhas são idênticas e falha de escrita aborta a operação.
3. Reconciliação detecta falta e divergência sem expor conteúdo ou modificar dados.
4. Restauração controlada recompõe IDs e horários ausentes e é idempotente.
5. Histórico de caso e eventos de identidade mantêm seus contratos.
