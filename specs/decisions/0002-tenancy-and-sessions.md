# ADR 0002: isolamento multitenant e sessões

Status: aceita em 2026-10-14.

## Decisão

Schema compartilhado com `organization_id` nas tabelas empresariais, FKs compostas e filtros obrigatórios por organização. Rotas empresariais usam `/organizations/{organization_id}/...`; a associação do usuário à organização e o papel são verificados no backend a cada requisição. Testes de acesso cruzado fazem parte do gate da Fase 2.

Sessões opacas armazenadas por hash no banco, cookie HttpOnly e SameSite=Lax, Secure em produção. Rotas mutáveis usam token CSRF ligado à sessão e validação de Origin. Senhas usam algoritmo de hash de memória com parâmetros versionados. Troca de papel ou remoção de associação invalida sessões quando aplicável.

## Consequências

O path torna o contexto explícito, mas nunca concede autorização por si. A aplicação deve impedir consultas sem escopo e testar também acesso indireto por IDs de outros tenants. PostgreSQL RLS pode ser avaliado como defesa adicional, sem substituir a autorização da API.
