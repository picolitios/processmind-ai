# ProcessMind AI

SaaS B2B de auditoria de compras empresariais. O MVP importa compras, aplica regras verificáveis, organiza achados em casos e usa IA local apenas para explicações ancoradas em evidências.

## Estado

Fases 0 e 1 concluídas. Funcionalidades de negócio começam na Fase 2. Consulte [plano](specs/implementation-plan.md) e [escopo](specs/product/mvp.md). Nenhum dado de dashboard deve ser tratado como real antes de existir persistência.

## Requisitos locais

- Windows com PowerShell, Docker Desktop e Docker Compose;
- Python 3.12 e Node.js 24 para execução e verificações fora dos contêineres;
- serviços gratuitos e locais. Ollama será necessário apenas na Fase 5.

## Documentação

- [Visão](specs/product/vision.md), [requisitos](specs/product/requirements.md) e [MVP](specs/product/mvp.md)
- [Arquitetura](specs/architecture/system-design.md), [modelo de dados](specs/architecture/data-model.md), [stack](specs/architecture/tech-stack.md)
- [Contrato OpenAPI planejado](specs/architecture/openapi.yaml), [segurança](specs/security/security-model.md), [testes](specs/testing/test-strategy.md)
- [Backlog e dependências](specs/implementation-plan.md), [ADRs](specs/decisions/)

O OpenAPI em `specs/` descreve o contrato alvo do MVP; endpoints ainda não implementados não são expostos pelo serviço.

## Fundação local (Fase 1)

No PowerShell, a partir da raiz:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
```

API: `http://localhost:8000/api/v1/health/live` e `/ready`. Web: `http://localhost:5173`. Antes de usar dados reais, substitua a senha local de `.env`; o mesmo valor precisa constar em `DATABASE_URL`. O Docker Desktop deve estar em execução. Para desenvolvimento sem Compose:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload
```

Em outro terminal:

```powershell
cd apps/web
npm ci
npm run dev
```

Verificações: `ruff check .`, `mypy app`, `pytest` em `apps/api`; `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` em `apps/web`. A CI executa a migração e o teste de readiness com PostgreSQL real. A migration `0001_foundation` é uma baseline sem tabelas de negócio; a primeira migração de entidades será da Fase 2. Ainda não há gerador de dados, upload nem interface funcional de auditoria.
