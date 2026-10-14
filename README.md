# ProcessMind AI

SaaS B2B de auditoria de compras empresariais. O MVP importa compras, aplica regras verificáveis, organiza achados em casos e usa IA local apenas para explicações ancoradas em evidências.

## Estado

Fases 0, 1 e 2 concluídas. A Fase 2 entrega a API de identidade, organizações e permissões; formulários e telas de negócio integram a Fase 6. Consulte [plano](specs/implementation-plan.md) e [escopo](specs/product/mvp.md). Nenhum dado de dashboard deve ser tratado como real antes de existir persistência.

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

Verificações: `ruff check .`, `mypy app`, `pytest` em `apps/api`; `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` em `apps/web`. A CI executa migrações e testes com PostgreSQL real. A migration `0001_foundation` é a baseline; as migrações seguintes criam identidade e o índice de retenção de falhas de login. Ainda não há gerador de dados, upload nem interface funcional de auditoria.

## API de identidade (Fase 2)

Os endpoints implementados constam em `/docs` da API e em `specs/architecture/openapi.yaml`. O fluxo é `POST /api/v1/auth/register` → `POST /api/v1/auth/login` → `POST /api/v1/organizations`. O login define um cookie HttpOnly e retorna `csrf_token`; envie esse valor no cabeçalho `X-CSRF-Token` em operações mutáveis autenticadas. O backend confere a associação e o papel em cada operação da organização. `Owner` pode associar usuários já cadastrados por email; convites por email não fazem parte desta fase.

O teste de integração local usa um banco separado. Para criá-lo e executar o gate da Fase 2:

```powershell
docker compose exec -T db psql -U processmind -d postgres -c 'CREATE DATABASE processmind_test'
cd apps/api
$env:DATABASE_URL='postgresql+psycopg://processmind:change-me-local@127.0.0.1:5432/processmind_test'
$env:RUN_DB_TESTS='1'
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\pytest
```

Se `processmind_test` já existir, pule apenas o comando `CREATE DATABASE`. Para uso fora do ambiente local, configure `APP_ENV` e uma chave `AUTH_HASH_KEY` aleatória de pelo menos 32 caracteres fora do repositório. O cookie fica `Secure` fora de `APP_ENV=local`.
