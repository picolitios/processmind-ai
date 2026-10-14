# ADR 0001: monólito modular

Status: aceita em 2026-10-14.

## Contexto

O MVP exige um fluxo transacional entre identidade, importação, auditoria, casos e trilha. O custo inicial é zero e o ambiente principal é local.

## Decisão

Um backend FastAPI com módulos por domínio, contratos internos explícitos e PostgreSQL único. Jobs demorados rodam em processo separado usando estado persistido no mesmo banco. A SPA é uma aplicação separada no monorepo.

## Consequências

Migrações e consistência transacional são simples. O worker pode escalar separadamente sem criar serviços de domínio. É necessário vigiar acoplamento entre módulos; comunicação por serviços/repositórios definidos, evitando importações cíclicas. Microsserviços só serão avaliados mediante gargalo demonstrado.
