# Reconciliação de referências à identidade — 2026-10-16

Ambiente: PostgreSQL local do Compose, com a migração `2e32182e442a` aplicada. Comando executado com a árvore de trabalho deste incremento:

```powershell
docker compose run --rm --no-deps -v "${PWD}\apps\api:/app" api python -m app.db.reconcile_identity
```

| Grupo | Verificações | IDs ausentes | Tenant de membro divergente |
| --- | ---: | ---: | ---: |
| Organização em tabelas de negócios | 14 | 0 | — |
| Usuário em importação, auditoria, IA e trilha | 4 | 0 | — |
| Membro responsável ou autor | 2 | 0 | 0 |
| **Total** | **20** | **0** | **0** |

O inventário de tabelas não apontou schema desconhecido. O comando retornou `0` (`clean`). A suíte Python passou em banco PostgreSQL novo (30 testes), incluindo uma referência órfã não persistida, detecção de tabela não classificada e falha técnica sem vazamento de detalhes.

Este relatório é um retrato do ambiente local. FKs existentes já impedem parte dos órfãos; as tabelas `audit_configurations` e `business_audit_events` não possuem essas FKs e também foram verificadas. Um resultado limpo não autoriza a remoção das constraints: ainda faltam política de exclusão, contratos de autorização/identificadores e rollback para cada referência.
