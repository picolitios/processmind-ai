# ADR 0004: propriedade da trilha de negócios

Status: aceito em 2026-10-15.

## Contexto

`audit_events` nasceu no módulo de identidade, mas registra também alterações de importação, auditoria, IA e casos dentro das transações de negócios. A leitura do histórico de caso depende dessa tabela. Remover a gravação direta sem outra persistência atômica perderia eventos em falhas de rede.

## Decisão

Criar uma trilha append-only de negócios com backfill e leitura própria. Durante a migração, gravar a trilha antiga e a nova na mesma transação, preservando rollback. A identidade continua proprietária dos eventos de autenticação e organização. A separação de credenciais aguarda a remoção da escrita legada após uma janela de reconciliação e um plano explícito de rollback.

## Consequências

O estado transitório ainda usa uma transação compartilhada. Um contrato de eventos ou outbox com reconciliação será necessário antes de separar bancos ou papéis. O histórico HTTP de caso não muda.
