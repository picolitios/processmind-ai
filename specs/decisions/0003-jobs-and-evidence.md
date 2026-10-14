# ADR 0003: jobs persistentes e evidência imutável

Status: aceita em 2026-10-14.

## Decisão

Importação, auditoria e análise de IA têm estados persistidos (`queued`, `running`, `succeeded`, `failed`) e identificador idempotente. Worker separado reivindica jobs por bloqueio transacional, registra tentativas e permite reprocessamento explícito. O upload original é preservado em armazenamento local privado por organização; no banco ficam caminho opaco, hash, metadados e linhas normalizadas. Backup deve incluir arquivos e banco.

Achados guardam versão da regra e snapshots de evidências estruturadas. Correções de dados geram nova importação/auditoria, sem reescrever evidência histórica. O LLM recebe apenas evidências verificadas e não altera valores críticos.

## Consequências

É preciso reconciliar arquivo e transação de banco após falha, além de limpeza de órfãos. O armazenamento local atende à execução inicial em uma máquina; migração futura para object storage exigirá abstração e ADR novos.
