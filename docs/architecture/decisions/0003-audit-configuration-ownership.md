# ADR 0003: propriedade da configuração de auditoria

Status: aceito em 2026-10-15. Decisão de produto: domínio de auditoria, preservando o contrato público.

## Contexto

A identidade armazena `settings` e `settings_version` em `organizations`. A auditoria bloqueia essa linha para copiar uma configuração versionada. O bloqueio evita snapshots inconsistentes, mas impede o isolamento de dados entre os domínios.

## Decisão

Adicionar `audit_configurations` ao domínio de auditoria e migrar leituras de criação de auditoria por modo controlado. Enquanto o banco for compartilhado, o endpoint existente grava ambas as representações em uma única transação, sob bloqueios de ordem fixa. Isso mantém dados e rollback de leitura sem transação distribuída. Uma falta de linha no modo novo é erro, sem fallback silencioso.

## Consequências

A nova tabela define a futura propriedade dos dados, mas a identidade ainda escreve nela e a auditoria ainda consulta `organizations` para associação e bloqueio. Este incremento não conclui o isolamento de credenciais. A etapa seguinte precisa substituir a gravação cruzada por contrato durável e resolver os outros vínculos descritos em `identity-data-cutover-plan.md` antes de separar papéis do banco.
